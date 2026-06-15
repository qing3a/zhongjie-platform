"""
L5 Collaboration - TaskService
Task 的高级服务: 状态变更发事件 + 轮询等待 + 统计
对应 P3 M18
"""
import logging
import threading
import time
from typing import Any

from ..infra.events import EventBus
from .task import Task, TaskState
from .task_manager import TaskManager

logger = logging.getLogger(__name__)


class TaskTimeoutError(Exception):
    pass


class TaskService:
    """Task 高级服务"""

    def __init__(self, task_manager: TaskManager, event_bus: EventBus | None = None) -> None:
        self._tm = task_manager
        self._bus = event_bus
        self._original_transition = None  # 用于 unpatch
        self._patched = False
        if event_bus is not None:
            self._patch_state_transitions()

    # ---------- 状态变更事件 hook ----------
    def _patch_state_transitions(self) -> None:
        """Monkey-patch Task.transition_to 以发事件
        简化实现：监听所有 tm.get(task).history 变化不现实
        改用显式方法 wrap_transition
        """
        # 实际 hook: 把 task 状态变更转换为 EventBus 事件
        # 此处不深 monkey patch, 留出显式方法
        self._patched = True

    def _emit_state_change(self, task: Task, from_state: TaskState | None, to_state: TaskState) -> None:
        if self._bus is None:
            return
        self._bus.emit(
            "task.state_changed",
            payload={
                "task_id": task.task_id,
                "context_id": task.context_id,
                "from_state": from_state.value if from_state else None,
                "to_state": to_state.value,
                "owner_agent_id": task.owner_agent_id,
            },
            source="task_service",
        )

    # ---------- 创建 ----------
    def create(
        self, kind: str, payload: dict, owner_agent_id: str | None = None,
        context_id: str | None = None, **kwargs,
    ) -> Task:
        """创建 task
        触发 task.created 事件
        """
        task = Task(kind=kind, payload=payload, owner_agent_id=owner_agent_id,
                    context_id=context_id, **kwargs)
        self._tm.create(task)
        if self._bus is not None:
            self._bus.emit("task.created", payload={
                "task_id": task.task_id, "kind": kind, "context_id": task.context_id,
            }, source="task_service")
        return task

    # ---------- 状态操作（带事件）----------
    def start(self, task_id: str, actor: str | None = None) -> Task:
        t = self._require(task_id)
        from_state = t.state
        t.start_working(actor=actor)
        self._tm._persist()
        self._emit_state_change(t, from_state, t.state)
        return t

    def request_input(self, task_id: str, actor: str | None = None, note: str = "") -> Task:
        t = self._require(task_id)
        from_state = t.state
        t.request_input(actor=actor, note=note)
        self._tm._persist()
        self._emit_state_change(t, from_state, t.state)
        return t

    def resume(self, task_id: str, actor: str | None = None) -> Task:
        t = self._require(task_id)
        from_state = t.state
        t.resume_from_input(actor=actor)
        self._tm._persist()
        self._emit_state_change(t, from_state, t.state)
        return t

    def complete(self, task_id: str, result: Any = None, actor: str | None = None) -> Task:
        t = self._require(task_id)
        # 便利 API: 如果还在 submitted，自动 start_working
        if t.state == TaskState.SUBMITTED:
            self.start(task_id, actor=actor)
            t = self._require(task_id)
        from_state = t.state
        t.complete(result=result, actor=actor)
        self._tm._persist()
        self._emit_state_change(t, from_state, t.state)
        if self._bus is not None:
            self._bus.emit("task.completed", payload={
                "task_id": t.task_id, "result": result,
                "owner_agent_id": t.owner_agent_id,
                "actor": actor or t.owner_agent_id,
            }, source="task_service")
        return t

    def fail(self, task_id: str, error: str, actor: str | None = None) -> Task:
        t = self._require(task_id)
        from_state = t.state
        t.fail(error=error, actor=actor)
        self._tm._persist()
        self._emit_state_change(t, from_state, t.state)
        if self._bus is not None:
            self._bus.emit("task.failed", payload={
                "task_id": t.task_id, "error": error,
                "owner_agent_id": t.owner_agent_id,
                "actor": actor or t.owner_agent_id,
            }, source="task_service")
        return t

    def cancel(self, task_id: str, actor: str | None = None, reason: str = "") -> Task:
        t = self._require(task_id)
        from_state = t.state
        t.cancel(actor=actor, reason=reason)
        self._tm._persist()
        self._emit_state_change(t, from_state, t.state)
        return t

    # ---------- 轮询 ----------
    def wait_for_completion(
        self, task_id: str, poll_interval: float = 0.1, timeout: float = 5.0,
    ) -> Task:
        """轮询直到 task 达到终态
        抛出 TaskTimeoutError 如果超时
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            t = self._tm.get(task_id)
            if t is None:
                raise TaskTimeoutError(f"Task '{task_id}' 不存在")
            if t.is_terminal():
                return t
            time.sleep(poll_interval)
        raise TaskTimeoutError(f"Task '{task_id}' 在 {timeout}s 内未达到终态")

    def get(self, task_id: str) -> Task | None:
        return self._tm.get(task_id)

    def list_active(self) -> list[Task]:
        return [t for t in self._tm.list_all() if t.is_active()]

    def list_terminal(self) -> list[Task]:
        return [t for t in self._tm.list_all() if t.is_terminal()]

    # ---------- 统计 ----------
    def stats(self) -> dict:
        all_tasks = self._tm.list_all()
        return {
            "total": len(all_tasks),
            "active": sum(1 for t in all_tasks if t.is_active()),
            "terminal": sum(1 for t in all_tasks if t.is_terminal()),
            "by_state": {
                state.value: sum(1 for t in all_tasks if t.state == state)
                for state in TaskState
            },
        }

    # ---------- 内部 ----------
    def _require(self, task_id: str) -> Task:
        t = self._tm.get(task_id)
        if t is None:
            raise TaskTimeoutError(f"Task '{task_id}' 不存在")
        return t
