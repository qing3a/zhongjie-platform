"""
L5 Collaboration - Task 状态机
对应交付物三的 P3 M15 + 交付物一的 A2A Task lifecycle

状态机:
    submitted → working → input-required → working → ... → completed
                  ↘                                  ↘
                    → completed / failed / canceled

设计:
- TaskState 枚举: 6 个状态
- Task dataclass: 状态历史/Artifacts/Payload
- 状态转换有合法性校验（不能从 completed 跳回 submitted）
- 状态变更记录在 history 列表
"""
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
from enum import Enum
from typing import Any
import uuid


class TaskState(str, Enum):
    """A2A Task 生命周期状态
    对应交付物一 A2A 协议规范
    """
    SUBMITTED = "submitted"            # 已提交
    WORKING = "working"                # 处理中
    INPUT_REQUIRED = "input-required"  # 需要输入（人工审批等）
    COMPLETED = "completed"            # 已完成
    FAILED = "failed"                  # 失败
    CANCELED = "canceled"              # 已取消


# 终态（不可再转换）
TERMINAL_STATES = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED}


# 合法状态转换
ALLOWED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.SUBMITTED: {TaskState.WORKING, TaskState.FAILED, TaskState.CANCELED},
    TaskState.WORKING: {TaskState.INPUT_REQUIRED, TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED},
    TaskState.INPUT_REQUIRED: {TaskState.WORKING, TaskState.FAILED, TaskState.CANCELED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELED: set(),
}


class InvalidTransitionError(Exception):
    """非法状态转换"""
    def __init__(self, from_state: TaskState, to_state: TaskState):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"非法状态转换: {from_state.value} → {to_state.value}")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class StateTransition:
    """一次状态转换的记录"""
    from_state: TaskState
    to_state: TaskState
    timestamp: str = field(default_factory=_now_iso)
    actor: str | None = None      # 谁触发
    note: str = ""


@dataclass
class TaskArtifact:
    """任务产物
    A2A 中 artifact 可以是大文件（如候选人简历），用 URL 引用避免大对象塞 Task
    """
    name: str
    type: str  # "candidate" / "match" / "report" / ...
    ref: str   # URL 或本地引用 ID
    metadata: dict = field(default_factory=dict)


@dataclass
class Task:
    """异步任务
    对应 A2A Protocol 的 task 实体
    """
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    context_id: str | None = None
    state: TaskState = TaskState.SUBMITTED
    kind: str = ""                       # "candidate_sourcing" / "jd_matching" / "delegate" ...
    payload: dict = field(default_factory=dict)
    artifacts: list[TaskArtifact] = field(default_factory=list)
    history: list[StateTransition] = field(default_factory=list)
    result: Any = None                   # 任务完成时的输出
    error: str | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    owner_agent_id: str | None = None    # 发起方

    def __post_init__(self) -> None:
        # 初始化 history（如果是新建）
        if not self.history and self.state == TaskState.SUBMITTED:
            self.history.append(StateTransition(
                from_state=TaskState.SUBMITTED,  # 占位
                to_state=TaskState.SUBMITTED,
                note="Task created",
            ))

    # ---------- 状态操作 ----------
    def transition_to(self, new_state: TaskState, actor: str | None = None, note: str = "") -> None:
        """转换状态
        非法转换抛 InvalidTransitionError
        终态不能再转换
        """
        if self.state in TERMINAL_STATES:
            raise InvalidTransitionError(self.state, new_state)
        allowed = ALLOWED_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise InvalidTransitionError(self.state, new_state)
        # 记录
        from_state = self.state
        self.state = new_state
        self.updated_at = _now_iso()
        self.history.append(StateTransition(
            from_state=from_state, to_state=new_state,
            actor=actor, note=note,
        ))

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def is_active(self) -> bool:
        return self.state in (TaskState.SUBMITTED, TaskState.WORKING, TaskState.INPUT_REQUIRED)

    # ---------- 便捷方法（语义化） ----------
    def start_working(self, actor: str | None = None) -> None:
        self.transition_to(TaskState.WORKING, actor=actor, note="Started processing")

    def request_input(self, actor: str | None = None, note: str = "") -> None:
        """如: 人工审批、等甲方回复"""
        self.transition_to(TaskState.INPUT_REQUIRED, actor=actor, note=note)

    def resume_from_input(self, actor: str | None = None) -> None:
        """input 收集完毕, 恢复 working"""
        self.transition_to(TaskState.WORKING, actor=actor, note="Resumed after input")

    def complete(self, result: Any = None, actor: str | None = None) -> None:
        self.transition_to(TaskState.COMPLETED, actor=actor, note="Task completed")
        self.result = result

    def fail(self, error: str, actor: str | None = None) -> None:
        self.transition_to(TaskState.FAILED, actor=actor, note=error)
        self.error = error

    def cancel(self, actor: str | None = None, reason: str = "") -> None:
        self.transition_to(TaskState.CANCELED, actor=actor, note=reason)

    # ---------- 产物 ----------
    def add_artifact(self, name: str, type: str, ref: str, metadata: dict | None = None) -> TaskArtifact:
        art = TaskArtifact(name=name, type=type, ref=ref, metadata=metadata or {})
        self.artifacts.append(art)
        return art

    # ---------- 序列化 ----------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        d["history"] = [
            {**asdict(h), "from_state": h.from_state.value, "to_state": h.to_state.value}
            for h in self.history
        ]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        d = dict(data)
        d["state"] = TaskState(d.get("state", "submitted"))
        history_raw = d.pop("history", [])
        history = [
            StateTransition(
                from_state=TaskState(h["from_state"]),
                to_state=TaskState(h["to_state"]),
                timestamp=h.get("timestamp", _now_iso()),
                actor=h.get("actor"),
                note=h.get("note", ""),
            )
            for h in history_raw
        ]
        d["history"] = history
        return cls(**d)
