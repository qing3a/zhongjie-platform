"""
L6 Protocol - Agent Card 服务
对应 P3 M17: 把 AgentRegistry 暴露为 A2A 标准的 Agent Card
- /.well-known/agent-card.json
- /a2a/agents/{agent_id}/card
- /a2a/agents (列表)
"""
import logging
from typing import Any

from ..identity.agent_card import AgentCard, AgentRole
from ..identity.registry import AgentRegistry

logger = logging.getLogger(__name__)


class AgentCardService:
    """Agent Card 服务
    把内部 AgentCard 转为 A2A 标准的 Agent Card JSON
    """
    PLATFORM_AGENT_CARD = {
        "name": "中介 API 平台 (zhongjie)",
        "description": "Agent 协作网络平台 - 支持猎头间委托/分润",
        "version": "1.0.0",
        "capabilities": {
            "streaming": True,
            "pushNotifications": True,
        },
        "skills": [
            {"id": "delegate", "name": "委托候选人给其他猎头"},
            {"id": "candidate_sourcing", "name": "候选人寻访"},
            {"id": "jd_matching", "name": "JD 匹配"},
        ],
        "authentication": {"schemes": ["bearer"]},
        "metadata": {
            "role": "platform",
            "endpoint": None,
        },
    }

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    # ---------- 平台卡 ----------
    def platform_card(self) -> dict:
        """返回平台自身的 Agent Card（用于 /.well-known/agent-card.json）"""
        return dict(self.PLATFORM_AGENT_CARD)

    # ---------- 单 agent 卡 ----------
    def get_card(self, agent_id: str) -> dict | None:
        """获取单个 agent 的 A2A Card
        不存在返回 None
        """
        card = self.registry.get(agent_id)
        if card is None:
            return None
        if not card.is_active():
            return None
        return card.to_a2a_card()

    # ---------- 列表 ----------
    def list_cards(
        self,
        role: AgentRole | None = None,
        capability: str | None = None,
        only_active: bool = True,
    ) -> list[dict]:
        """列出符合筛选条件的 agent cards
        role: 按角色筛
        capability: 按能力筛
        only_active: 是否仅活跃
        """
        if only_active:
            agents = self.registry.list_active()
        else:
            agents = self.registry.list_all()
        if role is not None:
            agents = [a for a in agents if a.role == role]
        if capability is not None:
            agents = [a for a in agents if capability in a.capabilities]
        return [a.to_a2a_card() for a in agents]

    # ---------- 统计 ----------
    def stats(self) -> dict:
        """聚合统计（用于监控）"""
        all_agents = self.registry.list_all()
        active = [a for a in all_agents if a.is_active()]
        suspended = [a for a in all_agents if a.status.value == "suspended"]
        revoked = [a for a in all_agents if a.status.value == "revoked"]
        avg_trust = (sum(a.trust_score for a in active) / len(active)) if active else 0.0
        return {
            "total": len(all_agents),
            "active": len(active),
            "suspended": len(suspended),
            "revoked": len(revoked),
            "avg_trust_score": round(avg_trust, 3),
            "by_role": {
                role.value: sum(1 for a in all_agents if a.role == role)
                for role in AgentRole
            },
        }
