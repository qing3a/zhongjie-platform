"""
P3 M18 测试 - TaskService 轮询 + 事件总线
"""
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.collaboration.task import TaskState
from zhongjie.collaboration.task_manager import TaskManager
from zhongjie.collaboration.task_service import TaskService, TaskTimeoutError
from zhongjie.infra.events import EventBus


@pytest.fixture
def service_no_bus(tmp_path):
    tm = TaskManager(data_dir=tmp_path)
    return TaskService(tm, event_bus=None), tm


@pytest.fixture
def service_with_bus(tmp_path):
    tm = TaskManager(data_dir=tmp_path)
    bus = EventBus()
    return TaskService(tm, event_bus=bus), tm, bus


def test_create_emits_event(service_with_bus):
    svc, tm, bus = service_with_bus
    received = []
    bus.subscribe("task.created", lambda e: received.append(e))
    t = svc.create(kind="test", payload={"k": 1}, owner_agent_id="hh-A")
    assert len(received) == 1
    assert received[0].payload["task_id"] == t.task_id
    assert received[0].payload["kind"] == "test"


def test_state_transitions_emit_events(service_with_bus):
    svc, _, bus = service_with_bus
    received = []
    bus.subscribe("task.state_changed", lambda e: received.append(e))
    t = svc.create(kind="test", payload={})
    svc.start(t.task_id)
    svc.request_input(t.task_id, note="等审批")
    svc.resume(t.task_id)
    svc.complete(t.task_id, result="ok")
    # 4 次状态变更
    assert len(received) == 4
    states = [e.payload["to_state"] for e in received]
    assert states == ["working", "input-required", "working", "completed"]


def test_completion_emits_completed_event(service_with_bus):
    svc, _, bus = service_with_bus
    received = []
    bus.subscribe("task.completed", lambda e: received.append(e))
    t = svc.create(kind="test", payload={})
    svc.complete(t.task_id, result={"matched": True})
    assert len(received) == 1
    assert received[0].payload["result"] == {"matched": True}


def test_no_event_bus_works_fine(service_no_bus):
    svc, _ = service_no_bus
    t = svc.create(kind="test", payload={})
    svc.complete(t.task_id)  # 不应抛异常
    assert t.state == TaskState.COMPLETED


def test_wait_for_completion_success(service_no_bus):
    svc, _ = service_no_bus
    t = svc.create(kind="test", payload={})
    # 模拟另一个线程完成 task
    import threading
    def completer():
        time.sleep(0.2)
        svc.complete(t.task_id)
    threading.Thread(target=completer, daemon=True).start()
    finished = svc.wait_for_completion(t.task_id, poll_interval=0.05, timeout=2.0)
    assert finished.state == TaskState.COMPLETED


def test_wait_for_completion_timeout(service_no_bus):
    svc, _ = service_no_bus
    t = svc.create(kind="test", payload={})
    svc.start(t.task_id)
    with pytest.raises(TaskTimeoutError):
        svc.wait_for_completion(t.task_id, poll_interval=0.05, timeout=0.3)


def test_wait_for_completion_already_terminal(service_no_bus):
    svc, _ = service_no_bus
    t = svc.create(kind="test", payload={})
    svc.complete(t.task_id)
    finished = svc.wait_for_completion(t.task_id, poll_interval=0.05, timeout=0.5)
    assert finished.state == TaskState.COMPLETED


def test_list_active_and_terminal(service_no_bus):
    svc, _ = service_no_bus
    t1 = svc.create(kind="a", payload={})
    t2 = svc.create(kind="b", payload={})
    svc.complete(t2.task_id)  # t2 终态
    active = svc.list_active()
    terminal = svc.list_terminal()
    assert t1.task_id in [t.task_id for t in active]
    assert t2.task_id not in [t.task_id for t in active]
    assert t2.task_id in [t.task_id for t in terminal]


def test_stats(service_no_bus):
    svc, _ = service_no_bus
    svc.create(kind="a", payload={})
    svc.create(kind="b", payload={})
    t3 = svc.create(kind="c", payload={})
    svc.complete(t3.task_id)
    stats = svc.stats()
    assert stats["total"] == 3
    assert stats["active"] == 2
    assert stats["terminal"] == 1
    assert stats["by_state"]["submitted"] == 2
    assert stats["by_state"]["completed"] == 1
