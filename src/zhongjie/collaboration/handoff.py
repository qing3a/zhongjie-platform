"""
L5 Collaboration - Handoff 候选人所有权转移
对应 P4 M22

Handoff vs Share 的区别:
- Share: 多人可见，原 owner 仍是 owner
- Handoff: 所有权彻底转移，from_agent 失去编辑权/分享权
"""
import logging
from typing import Literal

from ..domain.services import (
    CandidateNotFoundError, CandidateService, OwnerMismatchError
)
from ..infra.events import EventBus

logger = logging.getLogger(__name__)


class HandoffError(Exception):
    pass


class HandoffService:
    """所有权转移服务"""

    def __init__(
        self,
        candidate_service: CandidateService,
        event_bus: EventBus | None = None,
    ) -> None:
        self._cs = candidate_service
        self._bus = event_bus

    def handoff(
        self,
        candidate_id: str,
        from_agent_id: str,
        to_agent_id: str,
        ref_id: str | None = None,
        reset_visibility: bool = True,
        note: str = "",
    ) -> dict:
        """把候选人所有权从 from_agent_id 转给 to_agent_id
        流程:
        1. 验证 from_agent_id 是当前 owner
        2. 清空 shared_with（to_agent 仍能通过新 owner 身份看）
        3. owner_agent_id = to_agent_id
        4. visibility 视情况重置
        5. provenance 记录 "handed_off"
        返回 {"candidate": candidate, "from": from_agent_id, "to": to_agent_id}
        """
        if from_agent_id == to_agent_id:
            raise HandoffError("不能转移给自己")

        # 验证
        try:
            cand = self._cs.assert_owner(from_agent_id, candidate_id)
        except CandidateNotFoundError as e:
            raise HandoffError(f"候选人不存在: {e}")
        except OwnerMismatchError as e:
            raise HandoffError(f"所有权转移失败: {e}")

        # 记录 provenance（先记后改，确保完整链路）
        cand.add_provenance(
            action="handed_off",
            actor_agent_id=from_agent_id,
            target_agent_id=to_agent_id,
            ref_id=ref_id,
            note=note or f"Candidate ownership transferred from {from_agent_id} to {to_agent_id}",
        )
        # 改 owner
        cand.owner_agent_id = to_agent_id
        # 清空 shared_with（原所有方不再可见，除非被新 owner 加回）
        cand.shared_with = []
        # 可见性按需重置
        if reset_visibility:
            cand.visibility = "private"
        # 持久化
        self._cs._repo.save(cand)
        self._cs._repo.persist()
        # 事件
        if self._bus is not None:
            self._bus.emit("candidate.handed_off", payload={
                "candidate_id": candidate_id,
                "from_agent_id": from_agent_id,
                "to_agent_id": to_agent_id,
                "ref_id": ref_id,
            }, source="handoff_service")
        return {
            "candidate_id": candidate_id,
            "from": from_agent_id,
            "to": to_agent_id,
        }

    def can_handoff(self, from_agent_id: str, candidate_id: str) -> bool:
        """检查 from_agent 是否有权转移（= 是 owner）"""
        try:
            self._cs.assert_owner(from_agent_id, candidate_id)
            return True
        except (CandidateNotFoundError, OwnerMismatchError):
            return False
