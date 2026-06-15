"""
P3 M16 测试 - A2A Dispatcher + TaskManager
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.collaboration.task import Task, TaskState
from zhongjie.collaboration.task_manager import TaskManager
from zhongjie.protocol.a2a import A2A_ERROR_CODES, A2ADispatcher


@pytest.fixture
def dispatcher(tmp_path):
    tm = TaskManager(data_dir=tmp_path)
    return A2ADispatcher(task_manager=tm), tm


def test_a2a_tasks_send_creates_task(dispatcher):
    d, tm = dispatcher
    r = d.dispatch({
        "method": "tasks/send",
        "params": {
            "message": {"parts": [
                {"type": "data", "data": {"skill": "delegate", "candidate_id": "c1"}}
            ]},
            "sessionId": "ctx_test_1",
        },
        "id": "req-1",
    }, context={"agent_id": "hh-A"})
    # JSON-RPC envelope
    assert r["jsonrpc"] == "2.0"
    assert r["id"] == "req-1"
    assert "result" in r
    # 业务 result
    result = r["result"]
    assert result["status"] in ("pending", "success")
    task_data = result["data"]
    assert task_data["kind"] == "delegate"
    assert task_data["context_id"] == "ctx_test_1"
    assert task_data["owner_agent_id"] == "hh-A"


def test_a2a_tasks_get_returns_task(dispatcher):
    d, tm = dispatcher
    # 先 create
    create_r = d.dispatch({"method": "tasks/send", "params": {
        "message": {"parts": [{"type": "data", "data": {"skill": "x"}}]},
    }, "id": "1"})
    task_id = create_r["result"]["data"]["task_id"]
    # 然后 get
    r = d.dispatch({"method": "tasks/get", "params": {"id": task_id}, "id": "2"})
    assert r["result"]["status"] == "success"
    assert r["result"]["data"]["task_id"] == task_id


def test_a2a_tasks_get_not_found(dispatcher):
    d, _ = dispatcher
    r = d.dispatch({"method": "tasks/get", "params": {"id": "task_fake"}, "id": "x"})
    # 业务错误包在 result 里（A2A 设计: result = 业务响应, error = 协议级错误）
    assert "error" not in r  # 协议 envelope 无 error
    assert r["result"]["status"] == "error"
    assert r["result"]["code"] == "ERR_TASK_NOT_FOUND"


def test_a2a_tasks_cancel(dispatcher):
    d, _ = dispatcher
    create_r = d.dispatch({"method": "tasks/send", "params": {
        "message": {"parts": [{"type": "data", "data": {"skill": "x"}}]},
    }, "id": "1"})
    task_id = create_r["result"]["data"]["task_id"]
    r = d.dispatch({"method": "tasks/cancel", "params": {"id": task_id}, "id": "2"},
                   context={"agent_id": "hh-A"})
    assert r["result"]["status"] == "success"
    assert r["result"]["data"]["state"] == "canceled"


def test_a2a_tasks_cancel_terminal_fails(dispatcher):
    d, _ = dispatcher
    create_r = d.dispatch({"method": "tasks/send", "params": {
        "message": {"parts": [{"type": "data", "data": {"skill": "x"}}]},
    }, "id": "1"})
    task_id = create_r["result"]["data"]["task_id"]
    # 取消
    d.dispatch({"method": "tasks/cancel", "params": {"id": task_id}, "id": "2"})
    # 再次取消
    r = d.dispatch({"method": "tasks/cancel", "params": {"id": task_id}, "id": "3"})
    assert r["result"]["status"] == "error"
    assert r["result"]["code"] == "ERR_TASK_NOT_CANCELABLE"


def test_a2a_message_send_stateless(dispatcher):
    d, _ = dispatcher
    r = d.dispatch({"method": "message/send", "params": {
        "message": {"parts": [{"type": "data", "data": {"text": "hello"}}]},
    }, "id": "1"})
    assert r["result"]["status"] == "success"
    assert r["result"]["code"] == "A2A_MESSAGE_RECEIVED"
    assert r["result"]["data"]["echo"]["text"] == "hello"
    # 不创建 task
    assert d._tm.count() == 0


def test_a2a_unknown_method(dispatcher):
    d, _ = dispatcher
    r = d.dispatch({"method": "foo/bar", "params": {}, "id": "1"})
    assert "error" in r
    assert r["error"]["code"] == A2A_ERROR_CODES["METHOD_NOT_FOUND"]


def test_a2a_missing_method(dispatcher):
    d, _ = dispatcher
    r = d.dispatch({"params": {}, "id": "1"})  # 缺 method
    assert "error" in r
    assert r["error"]["code"] == A2A_ERROR_CODES["INVALID_REQUEST"]


def test_a2a_resume_existing_task(dispatcher):
    """推进已有 task: 进入 input-required 后 resume"""
    d, _ = dispatcher
    create_r = d.dispatch({"method": "tasks/send", "params": {
        "message": {"parts": [{"type": "data", "data": {"skill": "x"}}]},
    }, "id": "1"})
    task_id = create_r["result"]["data"]["task_id"]
    # 手动进入 input-required
    task = d._tm.get(task_id)
    task.request_input()
    # 推进
    r = d.dispatch({"method": "tasks/send", "params": {"id": task_id,
        "message": {"parts": []}}, "id": "2"})
    # 应该在 working
    assert r["result"]["data"]["state"] == "working"


def test_a2a_list_skills():
    d = A2ADispatcher(task_manager=TaskManager(data_dir="data"))
    skills = d.list_skills()
    assert len(skills) >= 1
    assert any(s["id"] == "delegate" for s in skills)


def test_task_manager_crud(tmp_path):
    tm = TaskManager(data_dir=tmp_path)
    t = Task(kind="test", owner_agent_id="hh-A")
    tm.create(t)
    assert tm.has(t.task_id)
    assert tm.count() == 1
    # get
    assert tm.get(t.task_id).task_id == t.task_id
    # list by owner
    owned = tm.list_by_owner("hh-A")
    assert len(owned) == 1
    assert tm.list_by_owner("hh-B") == []
    # delete
    assert tm.delete(t.task_id)
    assert tm.count() == 0
    assert tm.delete(t.task_id) is False  # 二次失败


def test_task_manager_persistence(tmp_path):
    """持久化: 一个实例 create，另一个实例 load"""
    tm1 = TaskManager(data_dir=tmp_path)
    t1 = Task(kind="test", owner_agent_id="hh-A")
    tm1.create(t1)

    tm2 = TaskManager(data_dir=tmp_path)
    assert tm2.has(t1.task_id)
    assert tm2.get(t1.task_id).kind == "test"


def test_task_manager_list_by_context(tmp_path):
    tm = TaskManager(data_dir=tmp_path)
    tm.create(Task(context_id="ctx_1", kind="a"))
    tm.create(Task(context_id="ctx_1", kind="b"))
    tm.create(Task(context_id="ctx_2", kind="c"))
    assert len(tm.list_by_context("ctx_1")) == 2
    assert len(tm.list_by_context("ctx_2")) == 1
