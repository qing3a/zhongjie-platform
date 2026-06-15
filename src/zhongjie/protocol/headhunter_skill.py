"""
猎头_skill 实现 - 基于新 domain service
对应老 api_server.py:1339-1444 的 4 个猎头 skill handler
【参考实现】 - 展示用新模块如何重写，等 M5 集成阶段再切换 api_server 调用
"""
from typing import Any

from ..domain.models import Candidate, JD, Match
from ..domain.services import CandidateService, JDService, MatchService
from .dispatcher import SkillHandler
from .responses import (
    ErrorCode, skill_error, skill_pending, skill_success
)


class HeadhunterSkill(SkillHandler):
    """猎头_skill
    actions: submit_jd, submit_candidate, submit_match, get_match_status
    """

    @property
    def skill_name(self) -> str:
        return "猎头_skill"

    @property
    def actions(self) -> list[str]:
        return ["submit_jd", "submit_candidate", "submit_match", "get_match_status"]

    def handle(self, action: str, data: dict, context: dict | None = None) -> dict:
        owner_agent_id = (context or {}).get("agent_id")
        if action == "submit_jd":
            return self._submit_jd(data, owner_agent_id)
        if action == "submit_candidate":
            return self._submit_candidate(data, owner_agent_id)
        if action == "submit_match":
            return self._submit_match(data)
        if action == "get_match_status":
            return self._get_match_status(data)
        return skill_error(ErrorCode.ERR_MISSING_PARAM, f"未知 action: {action}")

    # ---------- action 实现 ----------
    def _submit_jd(self, data: dict, owner_agent_id: str | None) -> dict:
        jd = self.jd.submit(data, owner_agent_id=owner_agent_id)
        return skill_success(
            ErrorCode.JD_SUBMITTED,
            {"jd_id": jd.id, "status": "active", "owner_agent_id": jd.owner_agent_id},
            f"JD '{jd.jd_title}' 已提交",
        )

    def _submit_candidate(self, data: dict, owner_agent_id: str | None) -> dict:
        cand = self.candidate.submit(data, owner_agent_id=owner_agent_id)
        return skill_success(
            ErrorCode.CANDIDATE_SUBMITTED,
            {"candidate_id": cand.id, "status": "active", "owner_agent_id": cand.owner_agent_id},
            f"候选人 '{cand.candidate_name}' 已提交（已脱敏）",
        )

    def _submit_match(self, data: dict) -> dict:
        match, err = self.match.submit(data)
        if err == "ERR_MISSING_PARAM":
            return skill_error(ErrorCode.ERR_MISSING_PARAM, "缺少必填参数: jd_id 或 candidate_id")
        if err == "ERR_NOT_FOUND_JD":
            return skill_error(ErrorCode.ERR_NOT_FOUND, f"JD '{data.get('jd_id')}' 不存在", 404)
        if err == "ERR_NOT_FOUND_CANDIDATE":
            return skill_error(ErrorCode.ERR_NOT_FOUND, f"候选人 '{data.get('candidate_id')}' 不存在", 404)
        if match is None:
            return skill_error(ErrorCode.ERR_INTERNAL, "提交失败")
        return skill_pending(
            ErrorCode.REQUEST_PENDING,
            {
                "match_id": match.id, "jd_id": match.jd_id,
                "candidate_id": match.candidate_id, "status": "pending",
                "created_at": match.created_at,
            },
            "匹配请求已提交，等待甲方确认",
        )

    def _get_match_status(self, data: dict) -> dict:
        match_id = data.get("match_id")
        if not match_id:
            return skill_error(ErrorCode.ERR_MISSING_PARAM, "缺少参数: match_id")
        match = self.match.get(match_id)
        if match is None:
            return skill_error(ErrorCode.ERR_NOT_FOUND, f"匹配记录 '{match_id}' 不存在", 404)
        return skill_success(
            ErrorCode.MATCH_STATUS_FETCHED,
            {
                "match_id": match.id, "jd_id": match.jd_id,
                "candidate_id": match.candidate_id, "status": match.status,
            },
            "匹配状态已获取",
        )
