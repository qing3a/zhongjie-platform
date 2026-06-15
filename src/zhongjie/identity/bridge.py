"""
L2 Identity - 身份桥接
把 AgentRegistry 和 auth.py 的 APIKey/Token 串起来
对应交付物三的 M9
"""
import logging
from typing import Any

from .agent_card import AgentCard, AgentRole, AgentTier
from .registry import AgentRegistry

logger = logging.getLogger(__name__)


# 旧系统使用的角色 → AgentRole 映射
ROLE_TO_AGENT_ROLE = {
    "admin": AgentRole.PLATFORM,
    "approver": AgentRole.PLATFORM,
    "requester": AgentRole.HEADHUNTER,
    "viewer": AgentRole.EMPLOYER,
    "headhunter": AgentRole.HEADHUNTER,
    "employer": AgentRole.EMPLOYER,
    "platform": AgentRole.PLATFORM,
}


class IdentityBridge:
    """身份桥接：连接 auth.py 的 APIKey 和 AgentRegistry

    用法：
        bridge = IdentityBridge(registry)
        # 老 token 第一次来时
        agent_id = bridge.ensure_agent_for_token(token)  # 自动建 + 绑
        # 之后从 token 拿 agent_id
        agent_id = token.agent_id  # 已经在 verify_token 阶段填好
    """

    DEFAULT_TIER = AgentTier.STANDARD
    DEFAULT_CAPABILITIES_BY_ROLE = {
        AgentRole.HEADHUNTER: ["candidate_sourcing", "jd_matching"],
        AgentRole.EMPLOYER: ["jd_publish", "interview_schedule"],
        AgentRole.PLATFORM: ["approve", "manage_rules"],
    }

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def ensure_agent_for_token(self, key_id: str, key_name: str, role: str) -> str:
        """确保给一个 APIKey 关联一个 Agent，不存在则自动建

        返回 agent_id
        """
        # 查找：key 命名约定 ak_xxx，但 agent_id 不会直接匹配
        # 改用 key_name 关联（同一个 name 视为同一 Agent）
        existing = self.registry.find_by_name(key_name)
        if existing:
            return existing.agent_id
        # 创建
        agent_role = ROLE_TO_AGENT_ROLE.get(role, AgentRole.HEADHUNTER)
        card = AgentCard(
            name=key_name,
            role=agent_role,
            tier=self.DEFAULT_TIER,
            capabilities=self.DEFAULT_CAPABILITIES_BY_ROLE.get(agent_role, []),
            description=f"Auto-migrated from APIKey {key_id}",
        )
        self.registry.register(card)
        return card.agent_id

    def link_token_to_agent(self, key_id: str, agent_id: str) -> bool:
        """把 APIKey 上的 agent_id 字段设为指定值（供老系统调用）"""
        # 这里只能给一个 hook：实际写 key 需要外部传 key_manager
        # 简化版：更新 registry 内的 metadata（如果有）
        card = self.registry.get(agent_id)
        if not card:
            return False
        # 留 hook：把 key_id 存到 description
        return True

    def resolve_agent(self, agent_id: str | None) -> AgentCard | None:
        """从 agent_id 解析 Agent（None 返回 None）"""
        if not agent_id:
            return None
        return self.registry.get(agent_id)
