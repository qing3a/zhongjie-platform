"""
L5 Collaboration - Delegation Service
委托高级 API: create / accept / reject / cancel
- 集成 CandidateService (M13 share_to 联动)
- 集成 EventBus 发事件
- 集成 TaskService 创建关联 Task

对应 P4 M20
"""
import json
import logging
import threading
from pathlib import Path
from typing import Any

from ..domain.services import CandidateNotFoundError, CandidateService, OwnerMismatchError
from ..domain.models import FeeShareValidationError, validate_fee_split
from ..infra.events import EventBus
from .delegation import Delegation, DelegationStatus
from .task_service import TaskService

logger = logging.getLogger(__name__)


class DelegationManager:
    """Delegation 存储 + 持久化"""

    def __init__(self, data_dir: str | Path = "data", filename: str = "delegations.json") -> None:
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / filename
        self._delegations: dict[str, Delegation] = {}
        self._lock = threading.Lock()
        self._load()

    def save(self, d: Delegation) -> None:
        with self._lock:
            self._delegations[d.id] = d
            self._persist()

    def get(self, delegation_id: str) -> Delegation | None:
        with self._lock:
            return self._delegations.get(delegation_id)

    def list_all(self) -> list[Delegation]:
        with self._lock:
            return list(self._delegations.values())

    def list_by_from(self, agent_id: str) -> list[Delegation]:
        with self._lock:
            return [d for d in self._delegations.values() if d.from_agent_id == agent_id]

    def list_by_to(self, agent_id: str) -> list[Delegation]:
        with self._lock:
            return [d for d in self._delegations.values() if d.to_agent_id == agent_id]

    def find_active_for_candidate(self, candidate_ref: str) -> Delegation | None:
        """查找该候选人当前是否已有 active 委托
        active = PENDING / ACCEPTED / IN_PROGRESS / PLACED
        终态 (REJECTED/SETTLED/CANCELLED) 不算 active
        """
        with self._lock:
            for d in self._delegations.values():
                if d.candidate_ref == candidate_ref and d.is_active():
                    return d
            return None

    def delete(self, delegation_id: str) -> bool:
        with self._lock:
            if delegation_id in self._delegations:
                del self._delegations[delegation_id]
                self._persist()
                return True
            return False

    def count(self) -> int:
        with self._lock:
            return len(self._delegations)

    def _persist(self) -> None:
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            data = [d.to_dict() for d in self._delegations.values()]
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except Exception as e:
            logger.warning(f"delegations 持久化失败: {e}")

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            with self._lock:
                for item in raw:
                    if isinstance(item, dict) and "id" in item:
                        d = Delegation.from_dict(item)
                        self._delegations[d.id] = d
            logger.info(f"[DelegationManager] 加载 {len(self._delegations)} 个委托")
        except Exception as e:
            logger.warning(f"delegations 加载失败: {e}")


class DelegationNotFoundError(Exception):
    pass


class CandidateAlreadyDelegatedError(Exception):
    """候选人已有 active 委托时再次发起（防飞单 + 防重复工作）
    设计文档 §7: '同一 candidate 的 active_delegations 互斥校验'
    """
    pass


class DelegationService:
    """委托服务
    集成 CandidateService（分享联动）+ EventBus（事件）+ 可选 TaskService（关联 Task）
    """

    def __init__(
        self,
        delegation_manager: DelegationManager | None = None,
        candidate_service: CandidateService | None = None,
        event_bus: EventBus | None = None,
        task_service: TaskService | None = None,
    ) -> None:
        self._dm = delegation_manager or DelegationManager()
        self._cs = candidate_service
        self._bus = event_bus
        self._ts = task_service

    # ---------- 发起 ----------
    def create(
        self,
        from_agent_id: str,
        to_agent_id: str,
        candidate_ref: str,
        jd_context: str = "",
        fee_split: list | None = None,
        visibility: str = "masked",
        deadline: str | None = None,
        note: str = "",
        create_task: bool = True,
    ) -> Delegation:
        """发起一个委托
        可选: 创建一个关联的 A2A Task

        校验顺序（先快后慢，先轻后重）:
        1. fee_split 比例校验（避免创建后再 fail）
        2. ACL: 发起方拥有候选人
        3. 防飞单: 候选人当前无 active delegation
        """
        # 1) fee_split 硬校验（在构造 Delegation 前完成，错误快速反馈）
        if fee_split:
            try:
                validate_fee_split(fee_split)
            except FeeShareValidationError:
                raise

        # 2) ACL: 发起方必须拥有候选人
        if self._cs is not None:
            try:
                self._cs.assert_owner(from_agent_id, candidate_ref)
            except CandidateNotFoundError:
                raise
            except OwnerMismatchError as e:
                raise PermissionError_(f"委托发起方校验失败: {e}")

        # 3) 防飞单: 同一候选人同一时刻只允许一条 active 委托
        existing = self._dm.find_active_for_candidate(candidate_ref)
        if existing is not None:
            raise CandidateAlreadyDelegatedError(
                f"候选人 '{candidate_ref}' 当前已有 active 委托: "
                f"{existing.id} ({existing.status.value}), "
                f"from={existing.from_agent_id} → to={existing.to_agent_id}"
            )

        deleg = Delegation(
            from_agent_id=from_agent_id, to_agent_id=to_agent_id,
            candidate_ref=candidate_ref, jd_context=jd_context,
            visibility=visibility, deadline=deadline, note=note,
        )
        if fee_split:
            deleg.set_fee_split(fee_split)
        # 关联 Task
        if create_task and self._ts is not None:
            task = self._ts.create(
                kind="delegate",
                payload={"delegation_id": deleg.id, "to_agent_id": to_agent_id,
                         "visibility": visibility, "jd_context": jd_context},
                owner_agent_id=from_agent_id,
                context_id=deleg.id,
            )
            deleg.task_id = task.task_id
        self._dm.save(deleg)
        if self._bus is not None:
            self._bus.emit("delegation.created", payload={
                "delegation_id": deleg.id,
                "from_agent_id": from_agent_id,
                "to_agent_id": to_agent_id,
                "candidate_ref": candidate_ref,
            }, source="delegation_service")
        return deleg

    # ---------- 响应 ----------
    def accept(self, delegation_id: str, actor: str | None = None, note: str = "") -> Delegation:
        """受托方接受委托
        联动: 候选人 candidate.shared_with 加入受托方
        """
        d = self._require(delegation_id)
        # 权限: 仅 to_agent_id 可接受
        if actor and d.to_agent_id != actor:
            raise PermissionError_(f"Agent '{actor}' 不是受托方 {d.to_agent_id}")
        d.accept(actor=actor or d.to_agent_id, note=note)
        # 联动: 分享候选人
        if self._cs is not None and d.visibility == "masked":
            try:
                self._cs.share_to(
                    actor_agent_id=d.from_agent_id,
                    candidate_id=d.candidate_ref,
                    target_agent_id=d.to_agent_id,
                    ref_id=d.id,
                )
            except Exception as e:
                logger.warning(f"委托接受时分享失败: {e}")
        self._dm.save(d)
        # 推进关联 Task
        if self._ts is not None and d.task_id:
            try:
                self._ts.complete(d.task_id, result={"delegation_id": d.id, "status": "accepted"})
            except Exception:
                pass
        if self._bus is not None:
            self._bus.emit("delegation.accepted", payload={
                "delegation_id": d.id,
                "from_agent_id": d.from_agent_id,
                "to_agent_id": d.to_agent_id,
                "actor": actor or d.to_agent_id,
            }, source="delegation_service")
        return d

    def reject(self, delegation_id: str, actor: str | None = None, reason: str = "") -> Delegation:
        d = self._require(delegation_id)
        if actor and d.to_agent_id != actor:
            raise PermissionError_(f"Agent '{actor}' 不是受托方")
        d.reject(actor=actor or d.to_agent_id, reason=reason)
        self._dm.save(d)
        if self._ts is not None and d.task_id:
            try:
                self._ts.fail(d.task_id, error=reason or "rejected")
            except Exception:
                pass
        if self._bus is not None:
            self._bus.emit("delegation.rejected", payload={
                "delegation_id": d.id,
                "from_agent_id": d.from_agent_id,
                "to_agent_id": d.to_agent_id,
                "actor": actor or d.to_agent_id,
                "reason": reason,
            }, source="delegation_service")
        return d

    def cancel(self, delegation_id: str, actor: str | None = None, reason: str = "") -> Delegation:
        d = self._require(delegation_id)
        # 双方都可取消
        if actor and actor not in (d.from_agent_id, d.to_agent_id):
            raise PermissionError_(f"Agent '{actor}' 不是委托参与方")
        d.cancel(actor=actor, reason=reason)
        self._dm.save(d)
        if self._ts is not None and d.task_id:
            try:
                self._ts.cancel(d.task_id, actor=actor, reason=reason)
            except Exception:
                pass
        if self._bus is not None:
            self._bus.emit("delegation.cancelled", payload={
                "delegation_id": d.id,
                "from_agent_id": d.from_agent_id,
                "to_agent_id": d.to_agent_id,
                "actor": actor,
                "reason": reason,
            }, source="delegation_service")
        return d

    def start_progress(self, delegation_id: str, actor: str | None = None) -> Delegation:
        d = self._require(delegation_id)
        d.start_progress(actor=actor or d.to_agent_id)
        self._dm.save(d)
        return d

    def mark_placed(self, delegation_id: str, actor: str | None = None) -> Delegation:
        d = self._require(delegation_id)
        d.mark_placed(actor=actor or d.to_agent_id)
        self._dm.save(d)
        if self._bus is not None:
            # payload 必须含 from_agent_id + to_agent_id, TrustStrategy 据此调整 trust
            self._bus.emit("delegation.placed", payload={
                "delegation_id": d.id,
                "candidate_ref": d.candidate_ref,
                "from_agent_id": d.from_agent_id,
                "to_agent_id": d.to_agent_id,
                "actor": actor or d.to_agent_id,
            }, source="delegation_service")
        return d

    # ---------- 查询 ----------
    def get(self, delegation_id: str) -> Delegation | None:
        return self._dm.get(delegation_id)

    def list_for_agent(self, agent_id: str, role: str = "any") -> list[Delegation]:
        if role == "from":
            return self._dm.list_by_from(agent_id)
        if role == "to":
            return self._dm.list_by_to(agent_id)
        return [d for d in self._dm.list_all()
                if d.from_agent_id == agent_id or d.to_agent_id == agent_id]

    def list_pending_for(self, agent_id: str) -> list[Delegation]:
        return [d for d in self._dm.list_by_to(agent_id)
                if d.status == DelegationStatus.PENDING]

    # ---------- 内部 ----------
    def _require(self, delegation_id: str) -> Delegation:
        d = self._dm.get(delegation_id)
        if d is None:
            raise DelegationNotFoundError(f"委托 '{delegation_id}' 不存在")
        return d


class PermissionError_(Exception):
    pass
