"""
L5 Collaboration - Delegation 委托实体
对应交付物二 "猎头 A 委托候选人给猎头 B 跟进" 场景

状态机:
    pending → accepted → in_progress → placed (成功) → settled (结算)
       ↘     ↘ → rejected   ↘ → cancelled        ↘
         → cancelled

字段:
- id: deleg_xxx
- from_agent_id: 委托方
- to_agent_id: 受托方
- candidate_ref: 候选人引用（只存 ref 不存明文，脱敏在 Domain 层）
- jd_context: 职位描述
- fee_split: 分润配置
- visibility: masked / full (脱敏/完整)
- status + 状态历史
- deadline
- candidate_handoff: True/False 是否完成所有权转移
"""
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
from enum import Enum
from typing import Any
import uuid

from ..domain.models import FeeShare, FeeShareValidationError, validate_fee_split


class DelegationStatus(str, Enum):
    """委托状态"""
    PENDING = "pending"          # 已发起, 等受托方响应
    ACCEPTED = "accepted"        # 受托方接受
    REJECTED = "rejected"        # 受托方拒绝
    IN_PROGRESS = "in_progress"  # 跟进中
    PLACED = "placed"            # 候选人已成功入职
    SETTLED = "settled"          # 费用已结算
    CANCELLED = "cancelled"      # 任一方取消


# 终态
_TERMINAL = {DelegationStatus.REJECTED, DelegationStatus.SETTLED, DelegationStatus.CANCELLED}

# 合法转换
ALLOWED: dict[DelegationStatus, set[DelegationStatus]] = {
    DelegationStatus.PENDING: {DelegationStatus.ACCEPTED, DelegationStatus.REJECTED, DelegationStatus.CANCELLED},
    DelegationStatus.ACCEPTED: {DelegationStatus.IN_PROGRESS, DelegationStatus.CANCELLED},
    DelegationStatus.IN_PROGRESS: {DelegationStatus.PLACED, DelegationStatus.CANCELLED},
    DelegationStatus.PLACED: {DelegationStatus.SETTLED, DelegationStatus.CANCELLED},
    DelegationStatus.REJECTED: set(),
    DelegationStatus.SETTLED: set(),
    DelegationStatus.CANCELLED: set(),
}


class InvalidDelegationTransitionError(Exception):
    def __init__(self, from_state: DelegationStatus, to_state: DelegationStatus):
        self.from_state, self.to_state = from_state, to_state
        super().__init__(f"非法委托状态转换: {from_state.value} → {to_state.value}")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class DelegationStateChange:
    from_state: DelegationStatus
    to_state: DelegationStatus
    timestamp: str = field(default_factory=_now_iso)
    actor: str | None = None
    note: str = ""


@dataclass
class Delegation:
    """委托关系"""
    id: str = field(default_factory=lambda: f"deleg_{uuid.uuid4().hex[:8]}")
    task_id: str | None = None                  # 关联 A2A Task
    from_agent_id: str = ""
    to_agent_id: str = ""
    candidate_ref: str = ""                     # candidate id 引用
    jd_context: str = ""
    fee_split: list[dict] = field(default_factory=list)
    visibility: str = "masked"                  # masked / full
    status: DelegationStatus = DelegationStatus.PENDING
    history: list[DelegationStateChange] = field(default_factory=list)
    deadline: str | None = None                 # ISO date
    note: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    decided_at: str | None = None
    candidate_handoff: bool = False             # 是否完成所有权转移

    def __post_init__(self) -> None:
        # 初始化 history
        if not self.history:
            self.history.append(DelegationStateChange(
                from_state=DelegationStatus.PENDING,
                to_state=DelegationStatus.PENDING,
                note="Delegation created",
            ))
        # fee_split 硬校验：失败抛 FeeShareValidationError
        # 设计承诺: 分润比例在委托发起时即"上链", 错误比例必须被拒绝
        if self.fee_split:
            validate_fee_split(self.fee_split)

    # ---------- 状态机 ----------
    def transition_to(self, new_state: DelegationStatus, actor: str | None = None, note: str = "") -> None:
        if self.status in _TERMINAL:
            raise InvalidDelegationTransitionError(self.status, new_state)
        if new_state not in ALLOWED.get(self.status, set()):
            raise InvalidDelegationTransitionError(self.status, new_state)
        from_state = self.status
        self.status = new_state
        self.updated_at = _now_iso()
        if new_state in (DelegationStatus.ACCEPTED, DelegationStatus.REJECTED):
            self.decided_at = _now_iso()
        self.history.append(DelegationStateChange(
            from_state=from_state, to_state=new_state, actor=actor, note=note,
        ))

    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    def is_active(self) -> bool:
        return self.status in (DelegationStatus.PENDING, DelegationStatus.ACCEPTED, DelegationStatus.IN_PROGRESS, DelegationStatus.PLACED)

    # ---------- 便捷方法 ----------
    def accept(self, actor: str | None = None, note: str = "") -> None:
        self.transition_to(DelegationStatus.ACCEPTED, actor=actor, note=note)

    def reject(self, actor: str | None = None, reason: str = "") -> None:
        self.transition_to(DelegationStatus.REJECTED, actor=actor, note=reason)

    def start_progress(self, actor: str | None = None) -> None:
        self.transition_to(DelegationStatus.IN_PROGRESS, actor=actor, note="开始跟进候选人")

    def mark_placed(self, actor: str | None = None) -> None:
        """候选人成功入职"""
        self.transition_to(DelegationStatus.PLACED, actor=actor, note="候选人已入职")

    def settle(self, actor: str | None = None) -> None:
        """费用已结算"""
        self.transition_to(DelegationStatus.SETTLED, actor=actor, note="分润已结算")

    def cancel(self, actor: str | None = None, reason: str = "") -> None:
        self.transition_to(DelegationStatus.CANCELLED, actor=actor, note=reason)

    # ---------- 业务方法 ----------
    def set_fee_split(self, shares: list[FeeShare] | list[dict]) -> None:
        """设置分润（验证 pct 之和 = 1.0）"""
        validate_fee_split(shares)
        normalized = []
        for s in shares:
            if isinstance(s, FeeShare):
                normalized.append(s.to_dict())
            else:
                normalized.append(s)
        self.fee_split = normalized

    def fee_share_for(self, agent_id: str) -> FeeShare | None:
        for s in self.fee_split:
            if s.get("agent_id") == agent_id:
                return FeeShare.from_dict(s)
        return None

    # ---------- 序列化 ----------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["history"] = [
            {**asdict(h), "from_state": h.from_state.value, "to_state": h.to_state.value}
            for h in self.history
        ]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Delegation":
        d = dict(data)
        d["status"] = DelegationStatus(d.get("status", "pending"))
        history_raw = d.pop("history", [])
        history = [
            DelegationStateChange(
                from_state=DelegationStatus(h["from_state"]),
                to_state=DelegationStatus(h["to_state"]),
                timestamp=h.get("timestamp", _now_iso()),
                actor=h.get("actor"),
                note=h.get("note", ""),
            )
            for h in history_raw
        ]
        d["history"] = history
        return cls(**d)
