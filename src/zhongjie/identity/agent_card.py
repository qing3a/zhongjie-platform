"""
L2 Identity - AgentCard 数据模型
对应交付物三的 M6 + 交付物一的 A2A Agent Card 适配

设计要点:
- Pydantic BaseModel（与其他 L4/L3 dataclass 不同，因为要导出 JSON / 校验）
- 字段对齐 A2A Agent Card（capabilities/skills/authentication）
- 信任分初始 0.5，范围 [0.0, 1.0]
"""
from datetime import UTC, datetime
from enum import Enum
from typing import Literal
import uuid

from pydantic import BaseModel, Field, field_validator


class AgentRole(str, Enum):
    """Agent 角色"""
    HEADHUNTER = "headhunter"
    EMPLOYER = "employer"
    PLATFORM = "platform"


class AgentTier(str, Enum):
    """Agent 等级（影响信任分初始化、配额、审批豁免）"""
    STANDARD = "standard"   # 默认
    SILVER = "silver"       # 试用合作
    GOLD = "gold"           # 战略合作


class AgentStatus(str, Enum):
    """Agent 状态"""
    ACTIVE = "active"
    SUSPENDED = "suspended"  # 临时停用
    REVOKED = "revoked"      # 永久吊销


def _gen_agent_id() -> str:
    return f"agent_{uuid.uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AgentCard(BaseModel):
    """Agent 身份卡片

    字段设计对齐 A2A Protocol Agent Card (见 design-01-a2a-adaptation.md)
    兼容字段：capabilities/skills/authentication
    扩展字段：trust_score/tier/status（治理增强）
    """
    # 基础身份
    agent_id: str = Field(default_factory=_gen_agent_id)
    name: str
    role: AgentRole
    tenant_id: str = "default"

    # 能力声明
    capabilities: list[str] = Field(default_factory=list)
    # 例如 ["candidate_sourcing", "finance", "jd_matching"]

    # 治理属性
    tier: AgentTier = AgentTier.STANDARD
    trust_score: float = 0.5  # 初始 0.5
    status: AgentStatus = AgentStatus.ACTIVE

    # 端点（用于 A2A 远程调用）
    endpoint: str | None = None
    auth_scheme: str = "bearer"

    # 元数据
    created_at: str = Field(default_factory=_now_iso)
    description: str = ""

    # ---------- 校验 ----------
    @field_validator("trust_score")
    @classmethod
    def _validate_trust(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"trust_score 必须在 [0.0, 1.0], got {v}")
        return v

    # ---------- 序列化 ----------
    def to_dict(self) -> dict:
        d = self.model_dump(mode="json")
        # enum 转字符串（Pydantic 已经在 mode='json' 自动转，但确保一致）
        d["role"] = self.role.value
        d["tier"] = self.tier.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentCard":
        # 兼容老数据（缺字段时用默认值）
        d = dict(data)
        if "role" in d and isinstance(d["role"], str):
            d["role"] = AgentRole(d["role"])
        if "tier" in d and isinstance(d["tier"], str):
            d["tier"] = AgentTier(d["tier"])
        if "status" in d and isinstance(d["status"], str):
            d["status"] = AgentStatus(d["status"])
        return cls(**d)

    # ---------- A2A 适配 ----------
    def to_a2a_card(self) -> dict:
        """导出 A2A Protocol 标准的 Agent Card
        服务于 /.well-known/agent-card.json 端点
        """
        return {
            "name": self.name,
            "description": self.description or f"{self.role.value} agent",
            "version": "1.0.0",
            "capabilities": {
                "streaming": True,
                "pushNotifications": True,
            },
            "skills": [
                {"id": cap, "name": cap, "inputModes": ["application/json"],
                 "outputModes": ["application/json"]}
                for cap in self.capabilities
            ],
            "authentication": {"schemes": [self.auth_scheme]},
            # 中介平台扩展（非 A2A 必需但本地有用）
            "metadata": {
                "agent_id": self.agent_id,
                "role": self.role.value,
                "tier": self.tier.value,
                "trust_score": self.trust_score,
                "status": self.status.value,
                "endpoint": self.endpoint,
            },
        }

    # ---------- 行为方法 ----------
    def can(self, capability: str) -> bool:
        """检查 Agent 是否具备某能力"""
        return capability in self.capabilities

    def is_active(self) -> bool:
        return self.status == AgentStatus.ACTIVE

    def update_trust(self, delta: float) -> float:
        """调整信任分（不越界）"""
        self.trust_score = max(0.0, min(1.0, self.trust_score + delta))
        return self.trust_score

    def suspend(self) -> None:
        self.status = AgentStatus.SUSPENDED

    def activate(self) -> None:
        self.status = AgentStatus.ACTIVE

    def revoke(self) -> None:
        self.status = AgentStatus.REVOKED
