"""
A2A 客户端测试 - 用 TestClient 模拟外部 Agent
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture
def client(monkeypatch, tmp_path):
    """FastAPI TestClient (隔离数据)"""
    monkeypatch.chdir(tmp_path)
    from zhongjie.api import deps
    deps.reset_all()
    from fastapi.testclient import TestClient
    from zhongjie.api.app import create_app
    yield TestClient(create_app())
    deps.reset_all()


def test_external_agent_full_flow(client):
    """模拟外部 Agent: 发现 → 注册 → 提交 Task → 查询 → 完成"""

    # 1. 发现平台
    r = client.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    assert "delegate" in [s["id"] for s in r.json()["skills"]]

    # 2. 注册自己
    r = client.post("/api/agents", json={
        "name": "ExternalAgent-1", "role": "headhunter",
        "capabilities": ["candidate_sourcing"],
    })
    assert r.status_code == 201
    my_id = r.json()["agent_id"]

    # 3. 提交 A2A Task
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-1",
        "method": "tasks/send",
        "params": {
            "message": {"parts": [{"type": "data",
                "data": {"skill": "candidate_sourcing", "jd": "P7 数据岗"}}]},
            "sessionId": "ctx-external-1",
        },
    })
    assert r.status_code == 200
    body = r.json()
    assert "result" in body
    task_id = body["result"]["data"]["task_id"]

    # 4. 查询 Task
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-2",
        "method": "tasks/get",
        "params": {"id": task_id},
    })
    assert r.status_code == 200
    assert r.json()["result"]["data"]["task_id"] == task_id

    # 5. 完成 Task
    r = client.post(f"/api/tasks/{task_id}/complete",
                    params={"result": {"matched": 3}})
    assert r.status_code == 200
    assert r.json()["state"] == "completed"

    # 6. 查自己 A2A Card
    r = client.get(f"/api/agents/{my_id}/card")
    assert r.status_code == 200
    card = r.json()
    assert card["metadata"]["agent_id"] == my_id


def test_a2a_message_send_stateless(client):
    """A2A 无状态消息"""
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "1",
        "method": "message/send",
        "params": {"message": {"parts": [{"type": "data", "data": {"hi": "there"}}]}},
    })
    assert r.status_code == 200
    assert r.json()["result"]["code"] == "A2A_MESSAGE_RECEIVED"


def test_a2a_jsonrpc_envelope_format(client):
    """A2A 响应严格遵守 JSON-RPC 2.0 envelope"""
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "test-123",
        "method": "tasks/send",
        "params": {"message": {"parts": [{"type": "data", "data": {"skill": "x"}}]}},
    })
    body = r.json()
    # 强制 envelope
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "test-123"
    # 业务 result 在 result 字段
    assert "result" in body
    assert body["result"]["status"] in ("success", "pending")


def test_a2a_invalid_method_returns_envelope_error(client):
    """未知方法 → JSON-RPC error envelope"""
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "1",
        "method": "foo/bar", "params": {},
    })
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == -32601  # METHOD_NOT_FOUND


def test_a2a_missing_method_invalid_request(client):
    """缺 method → INVALID_REQUEST"""
    r = client.post("/a2a", json={"jsonrpc": "2.0", "id": "1", "params": {}})
    body = r.json()
    assert body["error"]["code"] == -32600  # INVALID_REQUEST


def test_a2a_cancel_task(client):
    """A2A 取消 Task"""
    # 创建
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "1",
        "method": "tasks/send",
        "params": {"message": {"parts": [{"type": "data", "data": {"skill": "x"}}]}},
    })
    task_id = r.json()["result"]["data"]["task_id"]
    # 取消
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "2",
        "method": "tasks/cancel",
        "params": {"id": task_id},
    })
    assert r.json()["result"]["data"]["state"] == "canceled"


def test_a2a_two_agents_collaboration(client):
    """两个外部 Agent 完整协作: A 发起委托 → B 接受"""
    # 注册 A 和 B
    a_id = client.post("/api/agents", json={
        "name": "Agent-A", "role": "headhunter",
        "capabilities": ["candidate_sourcing"],
    }).json()["agent_id"]
    b_id = client.post("/api/agents", json={
        "name": "Agent-B", "role": "headhunter",
        "capabilities": ["finance"],
    }).json()["agent_id"]

    # A 录入候选人
    from zhongjie.domain.factory import build_services
    _, cand_svc, _ = build_services("data")
    cand = cand_svc.submit(
        {"candidate_name": "张三", "phone": "13800138000"},
        owner_agent_id=a_id,
    )

    # A 通过 HTTP 发起委托
    r = client.post("/api/delegations", json={
        "from_agent_id": a_id, "to_agent_id": b_id,
        "candidate_ref": cand.id, "jd_context": "P7 金融",
        "fee_split": [{"agent_id": a_id, "pct": 0.4}, {"agent_id": b_id, "pct": 0.6}],
    })
    assert r.status_code == 201
    deleg_id = r.json()["id"]

    # B 接受
    r = client.post(f"/api/delegations/{deleg_id}/accept", params={"actor": b_id})
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"
    # 候选人自动加入 B 的 shared_with
    cand_after = cand_svc.get(cand.id)
    assert b_id in cand_after.shared_with
