"""
L4 Domain Models - 纯数据类
对应老 api_server.py:1247-1249 的 _jd_storage / _candidate_storage / _match_storage 数据形状
"""
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ============ P2 新增: 可见性 + 来源链 ============

class Visibility(str, Enum):
    """候选人可见性
    private  - 仅 owner_agent_id 可见
    shared   - owner + shared_with 列表中的 agent 可见
    public   - 平台所有活跃 agent 可见（慎用）
    """
    PRIVATE = "private"
    SHARED = "shared"
    PUBLIC = "public"


@dataclass
class Provenance:
    """候选人来源链（防飞单关键）
    记录每一次"接触"或"转交"行为
    任何面试邀约必须带 provenance 中的 delegation_id 才能生效
    """
    action: str                  # "created" / "shared" / "delegated" / "contacted"
    actor_agent_id: str          # 谁做的
    target_agent_id: str | None  # 给谁（如果适用）
    ref_id: str | None = None    # 关联的 delegation_id / request_id
    timestamp: str = field(default_factory=_now_iso)
    note: str = ""


# ============ P2 新增: 分润（FeeShare） ============

@dataclass
class FeeShare:
    """分润份额
    多个 FeeShare 组成 match.fee_split
    所有 FeeShare.pct 之和必须等于 1.0（允许 ±0.001 浮点误差）
    """
    agent_id: str
    pct: float
    role: str = "co_finder"        # "owner" / "co_finder" / "platform_fee"
    settled: bool = False
    settled_at: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.pct <= 1.0:
            raise ValueError(f"FeeShare.pct 必须在 [0.0, 1.0], got {self.pct}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FeeShare":
        return cls(
            agent_id=data["agent_id"],
            pct=float(data["pct"]),
            role=data.get("role", "co_finder"),
            settled=data.get("settled", False),
            settled_at=data.get("settled_at"),
        )


class FeeShareValidationError(ValueError):
    """分润验证失败"""
    pass


def validate_fee_split(shares: list[FeeShare] | list[dict], tol: float = 1e-3) -> None:
    """验证一组 FeeShare 的 pct 之和 ≈ 1.0，agent_id 不重复
    失败抛 FeeShareValidationError
    """
    if not shares:
        raise FeeShareValidationError("fee_split 不能为空")
    # 统一转 FeeShare
    obj_shares = []
    for s in shares:
        if isinstance(s, dict):
            obj_shares.append(FeeShare.from_dict(s))
        else:
            obj_shares.append(s)
    # 总和
    total = sum(s.pct for s in obj_shares)
    if abs(total - 1.0) > tol:
        raise FeeShareValidationError(
            f"FeeShare pct 之和必须 = 1.0, got {total:.4f} (差 {abs(total-1.0):.4f})"
        )
    # agent_id 唯一
    agent_ids = [s.agent_id for s in obj_shares]
    if len(set(agent_ids)) != len(agent_ids):
        from collections import Counter
        dup = [k for k, v in Counter(agent_ids).items() if v > 1]
        raise FeeShareValidationError(f"FeeShare agent_id 重复: {dup}")


@dataclass
class JD:
    """职位需求
    对应老 _jd_storage 中的 jd_record
    字段保持向后兼容（老 JSON 文件不需修改）
    """
    id: str
    jd_title: str | None = None
    jd_level: str | None = None
    salary_range: str | None = None
    requirements: list[str] = field(default_factory=list)
    status: str = "active"
    created_at: str = field(default_factory=_now_iso)
    # 预留：P1 身份层接入时填充
    owner_agent_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "JD":
        # 兼容老数据：缺字段用默认值
        return cls(
            id=data["id"],
            jd_title=data.get("jd_title"),
            jd_level=data.get("jd_level"),
            salary_range=data.get("salary_range"),
            requirements=data.get("requirements", []),
            status=data.get("status", "active"),
            created_at=data.get("created_at", _now_iso()),
            owner_agent_id=data.get("owner_agent_id"),
        )


@dataclass
class Candidate:
    """候选人
    对应老 _candidate_storage 中的 candidate_record
    包含脱敏后的字段
    P2 增强: 加 visibility 枚举、provenance 来源链
    """
    id: str
    candidate_name: str | None = None
    experience: Any = None
    skills: list[str] = field(default_factory=list)
    expected_salary: Any = None
    phone: str = ""
    email: str = ""
    status: str = "active"
    created_at: str = field(default_factory=_now_iso)
    # 预留：P1/P2 接入
    owner_agent_id: str | None = None
    shared_with: list[str] = field(default_factory=list)
    visibility: str = "private"  # 字符串形式，兼容老 JSON；用 Visibility 枚举判断

    # P2 新增: 来源链
    provenance: list[dict] = field(default_factory=list)
    # 用 dict 而非 Provenance list 以兼容 JSON 序列化（Pydantic/dataclass 混用问题）

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Candidate":
        return cls(
            id=data["id"],
            candidate_name=data.get("candidate_name"),
            experience=data.get("experience"),
            skills=data.get("skills", []),
            expected_salary=data.get("expected_salary"),
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            status=data.get("status", "active"),
            created_at=data.get("created_at", _now_iso()),
            owner_agent_id=data.get("owner_agent_id"),
            shared_with=data.get("shared_with", []),
            visibility=data.get("visibility", "private"),
            provenance=data.get("provenance", []),
        )

    # ---------- P2 业务方法 ----------
    def add_provenance(self, action: str, actor_agent_id: str,
                       target_agent_id: str | None = None,
                       ref_id: str | None = None, note: str = "") -> None:
        """追加一条来源记录"""
        self.provenance.append({
            "action": action,
            "actor_agent_id": actor_agent_id,
            "target_agent_id": target_agent_id,
            "ref_id": ref_id,
            "timestamp": _now_iso(),
            "note": note,
        })

    def share_to(self, agent_id: str, actor_agent_id: str, ref_id: str | None = None) -> bool:
        """分享给 agent
        返回 False 表示已在列表中（无变化）
        自动: visibility → shared + 记录 provenance
        """
        if agent_id in self.shared_with:
            return False
        self.shared_with.append(agent_id)
        if self.visibility == "private":
            self.visibility = "shared"
        self.add_provenance(
            action="shared", actor_agent_id=actor_agent_id,
            target_agent_id=agent_id, ref_id=ref_id,
        )
        return True

    def unshare(self, agent_id: str) -> bool:
        """取消分享"""
        if agent_id in self.shared_with:
            self.shared_with.remove(agent_id)
            if not self.shared_with and self.visibility == "shared":
                self.visibility = "private"
            return True
        return False

    def can_be_viewed_by(self, agent_id: str) -> bool:
        """ACL: 该 agent 是否有权查看
        规则:
        - public → 任何活跃 agent 都能看
        - shared → owner + shared_with 列表中的 agent 能看
        - private → 仅 owner_agent_id 能看
        """
        v = Visibility(self.visibility)
        if v == Visibility.PUBLIC:
            return True
        if v == Visibility.SHARED:
            return agent_id == self.owner_agent_id or agent_id in self.shared_with
        # private
        return agent_id == self.owner_agent_id


@dataclass
class Match:
    """匹配记录
    对应老 _match_storage
    P2 增强: fee_split 结构化（list[dict]，每个 dict 是 FeeShare 序列化）
    """
    id: str
    jd_id: str | None = None
    candidate_id: str | None = None
    status: str = "pending"
    created_at: str = field(default_factory=_now_iso)
    # P2: 分润（agent_id -> pct）
    fee_split: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Match":
        return cls(
            id=data["id"],
            jd_id=data.get("jd_id"),
            candidate_id=data.get("candidate_id"),
            status=data.get("status", "pending"),
            created_at=data.get("created_at", _now_iso()),
            fee_split=data.get("fee_split", []),
        )

    # ---------- P2 业务方法 ----------
    def set_fee_split(self, shares: list[FeeShare] | list[dict]) -> None:
        """设置分润（自动验证 pct 之和）
        失败抛 FeeShareValidationError
        """
        validate_fee_split(shares)
        # 统一存为 dict 列表
        normalized: list[dict] = []
        for s in shares:
            if isinstance(s, FeeShare):
                normalized.append(s.to_dict())
            else:
                normalized.append(s)
        self.fee_split = normalized

    def fee_share_for(self, agent_id: str) -> FeeShare | None:
        """查询某 agent 的分润"""
        for s in self.fee_split:
            if s.get("agent_id") == agent_id:
                return FeeShare.from_dict(s)
        return None

    def total_pct(self) -> float:
        return sum(s.get("pct", 0.0) for s in self.fee_split)

    def is_valid_fee_split(self) -> bool:
        """检查当前 fee_split 是否合法（不抛异常）"""
        try:
            validate_fee_split(self.fee_split)
            return True
        except FeeShareValidationError:
            return False
