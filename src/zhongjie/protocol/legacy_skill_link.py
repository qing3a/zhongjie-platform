"""
Legacy Skill Link Dispatcher
兼容老 /skill/{skill_name}/{action} 协议
内部用新 domain service + SkillHandler 抽象实现
"""
from threading import Lock
from typing import Any

from ..domain.factory import build_services
from .dispatcher import ProtocolDispatcher, SkillHandler
from .headhunter_skill import HeadhunterSkill
from .responses import skill_error, ErrorCode


class LegacySkillLinkDispatcher(ProtocolDispatcher):
    """Legacy Skill Link 协议分发器

    老协议：POST /skill/{skill_name}/{action} body={...}
    新内部：用 SkillHandler 抽象 + domain service
    """

    def __init__(self, data_dir: str = "data") -> None:
        jd_svc, cand_svc, match_svc = build_services(data_dir)
        self._handlers: dict[str, SkillHandler] = {
            "猎头_skill": HeadhunterSkill(jd_svc, cand_svc, match_svc),
            # 后续可加: "甲方_skill": EmployerSkill(...), "平台_skill": PlatformSkill(...)
        }
        self._lock = Lock()

    def dispatch(self, request: dict, context: dict | None = None) -> dict:
        """分发一个请求
        request = {"skill_name": "猎头_skill", "action": "submit_jd", "data": {...}}
        """
        skill_name = request.get("skill_name")
        action = request.get("action")
        data = request.get("data", {})

        if not skill_name or not action:
            return skill_error(ErrorCode.ERR_MISSING_PARAM, "缺少 skill_name 或 action")

        handler = self._handlers.get(skill_name)
        if handler is None:
            return skill_error(ErrorCode.ERR_NOT_FOUND, f"未知 skill: {skill_name}", 404)
        if action not in handler.actions:
            return skill_error(ErrorCode.ERR_MISSING_PARAM, f"未知 action: {action}")

        return handler.handle(action, data, context)

    def list_skills(self) -> list[dict]:
        """列出所有暴露的 skills（类似 A2A Agent Card 用途）"""
        return [
            {
                "skill_name": h.skill_name,
                "actions": h.actions,
            }
            for h in self._handlers.values()
        ]
