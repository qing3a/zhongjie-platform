"""
L5 Collaboration - TaskManager
Task 的内存存储 + JSON 持久化 + 线程安全
对应 P3 M16/M18

支持:
- create / get / list
- 状态转换（委托给 Task 自己的状态机）
- 按 context_id 查询
- 持久化到 data/tasks.json
"""
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path

from .task import Task, TaskState

logger = logging.getLogger(__name__)


class TaskManager:
    """Task 管理器"""

    def __init__(self, data_dir: str | Path = "data", filename: str = "tasks.json") -> None:
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / filename
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._load()

    # ---------- CRUD ----------
    def create(self, task: Task | None = None, **kwargs) -> Task:
        """创建新 task
        可传入 Task 实例或关键字参数
        """
        if task is None:
            task = Task(**kwargs)
        with self._lock:
            self._tasks[task.task_id] = task
            self._persist()
        return task

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def has(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._tasks

    def list_all(self) -> list[Task]:
        with self._lock:
            return list(self._tasks.values())

    def list_by_context(self, context_id: str) -> list[Task]:
        with self._lock:
            return [t for t in self._tasks.values() if t.context_id == context_id]

    def list_by_owner(self, agent_id: str) -> list[Task]:
        with self._lock:
            return [t for t in self._tasks.values() if t.owner_agent_id == agent_id]

    def list_by_state(self, state: TaskState) -> list[Task]:
        with self._lock:
            return [t for t in self._tasks.values() if t.state == state]

    def delete(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                self._persist()
                return True
            return False

    def count(self) -> int:
        with self._lock:
            return len(self._tasks)

    # ---------- 持久化 ----------
    def _persist(self) -> None:
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            data = [t.to_dict() for t in self._tasks.values()]
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except Exception as e:
            logger.warning(f"tasks 持久化失败: {e}")

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            with self._lock:
                for item in raw:
                    if isinstance(item, dict) and "task_id" in item:
                        t = Task.from_dict(item)
                        self._tasks[t.task_id] = t
            logger.info(f"[TaskManager] 加载 {len(self._tasks)} 个 Task")
        except Exception as e:
            logger.warning(f"tasks 加载失败: {e}")
