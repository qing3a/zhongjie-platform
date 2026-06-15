"""
领域服务层 - 业务逻辑封装
对应老 api_server.py:1339-1444 的 4 个猎头 skill handler
"""
from pathlib import Path
import uuid

from .masking import mask_sensitive_data
from .models import Candidate, JD, Match
from .repositories import InMemoryRepository


class JDService:
    def __init__(self, repo: InMemoryRepository[JD]) -> None:
        self._repo = repo

    def submit(self, jd_data: dict, owner_agent_id: str | None = None) -> JD:
        jd_id = f"jd_{uuid.uuid4().hex[:8]}"
        record = JD(
            id=jd_id,
            jd_title=jd_data.get("jd_title"),
            jd_level=jd_data.get("jd_level"),
            salary_range=jd_data.get("salary_range"),
            requirements=jd_data.get("requirements", []),
            owner_agent_id=owner_agent_id,
        )
        self._repo.save(record)
        self._repo.persist()
        return record

    def get(self, jd_id: str) -> JD | None:
        return self._repo.get(jd_id)

    def list_all(self) -> list[JD]:
        return self._repo.list_all()


class CandidateService:
    def __init__(self, repo: InMemoryRepository[Candidate]) -> None:
        self._repo = repo

    def submit(self, candidate_data: dict, owner_agent_id: str | None = None) -> Candidate:
        candidate_id = f"cand_{uuid.uuid4().hex[:8]}"
        masked = mask_sensitive_data({
            "candidate_name": candidate_data.get("candidate_name"),
            "experience": candidate_data.get("experience"),
            "skills": candidate_data.get("skills", []),
            "expected_salary": candidate_data.get("expected_salary"),
            "phone": candidate_data.get("phone", ""),
            "email": candidate_data.get("email", ""),
        })
        record = Candidate(
            id=candidate_id,
            owner_agent_id=owner_agent_id,
            **masked,
        )
        # 记录 provenance
        if owner_agent_id:
            record.add_provenance(
                action="created",
                actor_agent_id=owner_agent_id,
                note=f"Candidate '{record.candidate_name}' created",
            )
        self._repo.save(record)
        self._repo.persist()
        return record

    def get(self, candidate_id: str) -> Candidate | None:
        return self._repo.get(candidate_id)

    def list_all(self) -> list[Candidate]:
        return self._repo.list_all()

    # ---------- P2 M13: 委托/分享（带发起方检查）----------
    def assert_owner(self, agent_id: str, candidate_id: str) -> Candidate:
        """验证 agent 是 candidate 的 owner
        失败抛 (None, error_code) 风格的 OwnerMismatchError
        成功返回 candidate
        """
        cand = self._repo.get(candidate_id)
        if cand is None:
            raise CandidateNotFoundError(f"候选人 '{candidate_id}' 不存在")
        if cand.owner_agent_id != agent_id:
            raise OwnerMismatchError(
                f"Agent '{agent_id}' 不是候选人 '{candidate_id}' 的 owner"
                f" (actual owner: {cand.owner_agent_id})"
            )
        return cand

    def share_to(
        self, actor_agent_id: str, candidate_id: str, target_agent_id: str,
        ref_id: str | None = None,
    ) -> tuple[bool, str | None]:
        """分享候选人给 target_agent_id
        返回 (success, error_code)
        错误码: ERR_CANDIDATE_NOT_FOUND / ERR_NOT_OWNER / ERR_SELF_SHARE
        """
        try:
            cand = self.assert_owner(actor_agent_id, candidate_id)
        except (CandidateNotFoundError, OwnerMismatchError) as e:
            err = "ERR_CANDIDATE_NOT_FOUND" if isinstance(e, CandidateNotFoundError) else "ERR_NOT_OWNER"
            return False, err
        if target_agent_id == actor_agent_id:
            return False, "ERR_SELF_SHARE"
        success = cand.share_to(target_agent_id, actor_agent_id, ref_id)
        if success:
            self._repo.save(cand)
            self._repo.persist()
        return success, None

    def unshare(
        self, actor_agent_id: str, candidate_id: str, target_agent_id: str,
    ) -> tuple[bool, str | None]:
        try:
            cand = self.assert_owner(actor_agent_id, candidate_id)
        except (CandidateNotFoundError, OwnerMismatchError) as e:
            err = "ERR_CANDIDATE_NOT_FOUND" if isinstance(e, CandidateNotFoundError) else "ERR_NOT_OWNER"
            return False, err
        success = cand.unshare(target_agent_id)
        if success:
            self._repo.save(cand)
            self._repo.persist()
        return success, None


# 异常
class CandidateNotFoundError(Exception):
    pass


class OwnerMismatchError(Exception):
    pass


class MatchService:
    def __init__(
        self,
        repo: InMemoryRepository[Match],
        jd_service: JDService,
        candidate_service: CandidateService,
    ) -> None:
        self._repo = repo
        self._jd = jd_service
        self._candidate = candidate_service

    def submit(self, match_data: dict) -> tuple[Match | None, str | None]:
        """返回 (Match, None) 成功；或 (None, error_code)"""
        jd_id = match_data.get("jd_id")
        candidate_id = match_data.get("candidate_id")
        if not jd_id or not candidate_id:
            return None, "ERR_MISSING_PARAM"
        if not self._jd.get(jd_id):
            return None, "ERR_NOT_FOUND_JD"
        if not self._candidate.get(candidate_id):
            return None, "ERR_NOT_FOUND_CANDIDATE"

        match_id = f"match_{uuid.uuid4().hex[:8]}"
        record = Match(
            id=match_id,
            jd_id=jd_id,
            candidate_id=candidate_id,
            status="pending",
        )
        self._repo.save(record)
        self._repo.persist()
        return record, None

    def get(self, match_id: str) -> Match | None:
        return self._repo.get(match_id)

    def list_all(self) -> list[Match]:
        return self._repo.list_all()
