"""
L3 Governance Models - 治理层数据模型
对应老 p0_core.py:14-57 的 RequestStatus/ActionType/Request
保持字段完全兼容，老 JSON 数据可零修改迁移
"""
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
from enum import Enum
from typing import Any
import uuid


class RequestStatus(str, Enum):
    """请求生命周期状态
    对应老 p0_core.py:14-19
    P1 接入后会与 A2A TaskState 双向映射
    """
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ROUTING = "routing"
    COMPLETED = "completed"


class ActionType(str, Enum):
    """规则命中后的动作
    对应老 p0_core.py:21-25
    """
    AUTO_APPROVE = "auto_approve"
    AUTO_REJECT = "auto_reject"
    MANUAL_REVIEW = "manual_review"
    ROUTE_DIRECTLY = "route_directly"


class Decision(str, Enum):
    """审批决策
    来自老 p1_p2.py:Decision 枚举（MediatorAPI 审批路径）
    """
    APPROVED = "approved"
    REJECTED = "rejected"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Request:
    """中介请求（治理对象）
    对应老 p0_core.py:27-57
    字段完全兼容，老 JSON 数据可零修改解析
    """
    source: str
    target: str
    intent: str
    payload: dict
    metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"req_{uuid.uuid4().hex[:8]}")
    status: RequestStatus = RequestStatus.PENDING
    created_at: str = field(default_factory=_now_iso)
    # 预留：P1 身份层接入
    requester_agent_id: str | None = None
    tenant_id: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value  # 枚举转字符串
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Request":
        return cls(
            id=data.get("id", f"req_{uuid.uuid4().hex[:8]}"),
            source=data["source"],
            target=data["target"],
            intent=data["intent"],
            payload=data.get("payload", {}),
            metadata=data.get("metadata", {}),
            status=RequestStatus(data.get("status", "pending")),
            created_at=data.get("created_at", _now_iso()),
            requester_agent_id=data.get("requester_agent_id"),
            tenant_id=data.get("tenant_id"),
        )
