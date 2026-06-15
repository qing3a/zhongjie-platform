"""
L3 Governance - 访问控制 (Access Control)

对应 P2 M12: 让领域对象 (Candidate/JD/Match) 的所有权/可见性真正落地
- 平台 admin 可看所有
- owner 可看自己创建/拥有的
- shared_with 可看被分享的
- public 任何活跃 agent 可看

不在 P2 范围: 委托场景 (P4 阶段扩展)
"""
from typing import Iterable

from ..domain.models import Candidate, JD, Match


class PermissionError_(Exception):
    """ACL 拒绝"""
    def __init__(self, action: str, agent_id: str, target_id: str):
        self.action = action
        self.agent_id = agent_id
        self.target_id = target_id
        super().__init__(f"Agent '{agent_id}' 无权 {action} '{target_id}'")


class AccessControl:
    """访问控制服务

    用法:
        acl = AccessControl()
        if acl.can_view_candidate(agent_id, candidate):
            ...
    """

    # 平台特权角色（来自 auth.py）
    PLATFORM_ROLES = {"admin", "approver", "platform"}

    def __init__(self, agent_roles: dict[str, str] | None = None) -> None:
        """agent_roles: {agent_id: role} 映射
        简化：M12 阶段手动注入；后续可从 auth.py 自动获取
        """
        self._roles = agent_roles or {}

    def set_role(self, agent_id: str, role: str) -> None:
        self._roles[agent_id] = role

    def is_platform_admin(self, agent_id: str) -> bool:
        return self._roles.get(agent_id, "") in self.PLATFORM_ROLES

    # ---------- Candidate ----------
    def can_view_candidate(self, agent_id: str, candidate: Candidate) -> bool:
        if self.is_platform_admin(agent_id):
            return True
        return candidate.can_be_viewed_by(agent_id)

    def can_edit_candidate(self, agent_id: str, candidate: Candidate) -> bool:
        """仅 owner 可编辑（管理员也可）"""
        if self.is_platform_admin(agent_id):
            return True
        return candidate.owner_agent_id == agent_id

    def can_share_candidate(self, agent_id: str, candidate: Candidate) -> bool:
        """仅 owner 可分享"""
        return self.can_edit_candidate(agent_id, candidate)

    def assert_can_view_candidate(self, agent_id: str, candidate: Candidate) -> None:
        if not self.can_view_candidate(agent_id, candidate):
            raise PermissionError_("view", agent_id, candidate.id)

    def assert_can_edit_candidate(self, agent_id: str, candidate: Candidate) -> None:
        if not self.can_edit_candidate(agent_id, candidate):
            raise PermissionError_("edit", agent_id, candidate.id)

    def filter_visible_candidates(
        self, agent_id: str, candidates: Iterable[Candidate]
    ) -> list[Candidate]:
        """过滤出 agent 可见的候选人"""
        return [c for c in candidates if self.can_view_candidate(agent_id, c)]

    # ---------- JD ----------
    def can_view_jd(self, agent_id: str, jd: JD) -> bool:
        # JD 默认是公开的（猎头之间共享需求），但可加 owner 限制
        # 简化: 平台 + 平台所有活跃 headhunter/employer 都可看 JD
        if self.is_platform_admin(agent_id):
            return True
        # JD 没有任何 ACL 字段时，所有人可看
        if jd.owner_agent_id is None:
            return True
        # 有 owner 时，仅 owner + 平台可看
        return jd.owner_agent_id == agent_id

    def can_edit_jd(self, agent_id: str, jd: JD) -> bool:
        if self.is_platform_admin(agent_id):
            return True
        return jd.owner_agent_id == agent_id

    # ---------- Match ----------
    def can_view_match(self, agent_id: str, match: Match) -> bool:
        """Match 涉及 JD + Candidate，agent 能看 match 当且仅当：
        - 平台管理员
        - 在 fee_split 中（co_finder）
        """
        if self.is_platform_admin(agent_id):
            return True
        for share in match.fee_split:
            if share.get("agent_id") == agent_id:
                return True
        return False

    def filter_visible_matches(
        self, agent_id: str, matches: Iterable[Match]
    ) -> list[Match]:
        return [m for m in matches if self.can_view_match(agent_id, m)]
