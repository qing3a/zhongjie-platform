"""
P3 M15 测试 - Task 状态机
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.collaboration.task import (
    InvalidTransitionError, StateTransition, Task, TaskArtifact, TaskState,
    TERMINAL_STATES
)


def test_task_default_state():
    t = Task()
    assert t.state == TaskState.SUBMITTED
    assert t.is_active()
    assert not t.is_terminal()


def test_task_lifecycle_happy_path():
    """正常生命周期: submitted → working → completed"""
    t = Task()
    t.start_working()
    assert t.state == TaskState.WORKING
    t.complete(result={"matched": True})
    assert t.state == TaskState.COMPLETED
    assert t.is_terminal()
    assert t.result == {"matched": True}


def test_task_input_required_loop():
    """input-required 循环: working → input-required → working → completed"""
    t = Task()
    t.start_working()
    t.request_input(note="等待甲方补充 JD")
    assert t.state == TaskState.INPUT_REQUIRED
    t.resume_from_input()
    assert t.state == TaskState.WORKING
    t.complete()
    assert t.state == TaskState.COMPLETED


def test_task_failure_path():
    t = Task()
    t.start_working()
    t.fail("网络错误")
    assert t.state == TaskState.FAILED
    assert t.error == "网络错误"
    assert t.is_terminal()


def test_task_cancel_path():
    t = Task()
    t.cancel(reason="用户撤回")
    assert t.state == TaskState.CANCELED
    assert t.is_terminal()


def test_terminal_state_no_more_transition():
    """终态不能再转换"""
    t = Task()
    t.start_working()
    t.complete()
    with pytest.raises(InvalidTransitionError):
        t.start_working()
    with pytest.raises(InvalidTransitionError):
        t.cancel()


def test_invalid_transition_raises():
    """submitted → completed 非法（必须先 working）"""
    t = Task()
    with pytest.raises(InvalidTransitionError):
        t.complete()


def test_state_history_recorded():
    """每次状态转换都记入 history"""
    t = Task()
    t.start_working(actor="hh-A")
    t.request_input(actor="system", note="等审批")
    t.resume_from_input(actor="approver1")
    t.complete(result="ok", actor="hh-A")

    # history: SUBMITTED (init) → WORKING → INPUT_REQUIRED → WORKING → COMPLETED
    transitions = [(h.from_state, h.to_state) for h in t.history]
    assert transitions[0] == (TaskState.SUBMITTED, TaskState.SUBMITTED)  # 初始
    assert transitions[1] == (TaskState.SUBMITTED, TaskState.WORKING)
    assert transitions[2] == (TaskState.WORKING, TaskState.INPUT_REQUIRED)
    assert transitions[3] == (TaskState.INPUT_REQUIRED, TaskState.WORKING)
    assert transitions[4] == (TaskState.WORKING, TaskState.COMPLETED)
    # 记录 actor
    assert t.history[1].actor == "hh-A"


def test_task_artifacts():
    t = Task()
    t.start_working()
    t.add_artifact("candidate_resume", "candidate", "cand_123", {"masked": True})
    t.add_artifact("jd_full", "jd", "jd_456")
    assert len(t.artifacts) == 2
    assert t.artifacts[0].name == "candidate_resume"


def test_task_round_trip_serialization():
    t = Task(task_id="task_1", context_id="ctx_1", kind="delegate", owner_agent_id="hh-A")
    t.start_working()
    t.complete(result={"ok": True})
    d = t.to_dict()
    t2 = Task.from_dict(d)
    assert t2.task_id == "task_1"
    assert t2.context_id == "ctx_1"
    assert t2.state == TaskState.COMPLETED
    assert t2.kind == "delegate"
    assert t2.owner_agent_id == "hh-A"
    assert t2.result == {"ok": True}
    # history 也保留
    assert len(t2.history) == len(t.history)


def test_task_from_legacy_dict():
    """兼容老 JSON 数据"""
    legacy = {
        "task_id": "task_old", "state": "working",
        "context_id": "ctx_1", "kind": "test",
    }
    t = Task.from_dict(legacy)
    assert t.state == TaskState.WORKING


def test_all_six_states_exist():
    """A2A 6 状态齐全"""
    states = {s.value for s in TaskState}
    assert states == {
        "submitted", "working", "input-required",
        "completed", "failed", "canceled"
    }


def test_terminal_states_set():
    """3 个终态"""
    assert TERMINAL_STATES == {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED}
