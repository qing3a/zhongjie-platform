"""
API 集成测试 - 端到端验证 FastAPI 路由
使用 chdir 隔离数据目录
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture
def isolated_data(monkeypatch, tmp_path):
    """把 data/ 重定向到隔离目录"""
    d = tmp_path / "data"
    d.mkdir()
    # 改 cwd → 所有 "data" 相对路径都解析到 tmp
    monkeypatch.chdir(tmp_path)
    # 重置所有 lru_cache
    from zhongjie.api import deps
    deps.reset_all()
    yield d
    deps.reset_all()


@pytest.fixture
def client(isolated_data):
    """FastAPI TestClient"""
    from fastapi.testclient import TestClient
    from zhongjie.api.app import create_app
    app = create_app()
    return TestClient(app)


# ============ /health & / ============
def test_root_and_health(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "endpoints" in r.json()
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ============ Agents ============
def test_register_and_list_agents(client):
    r = client.post("/api/agents", json={
        "name": "智联猎头", "role": "headhunter",
        "capabilities": ["finance", "jd_matching"],
    })
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "智联猎头"
    assert data["role"] == "headhunter"
    agent_id = data["agent_id"]

    # 列表
    r = client.get("/api/agents")
    assert r.status_code == 200
    listing = r.json()
    assert listing["total"] == 1
    assert listing["agents"][0]["agent_id"] == agent_id

    # 查单个
    r = client.get(f"/api/agents/{agent_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "智联猎头"


def test_get_agent_card_a2a_format(client):
    r = client.post("/api/agents", json={
        "name": "X", "role": "headhunter", "capabilities": ["finance"],
    })
    aid = r.json()["agent_id"]
    r = client.get(f"/api/agents/{aid}/card")
    assert r.status_code == 200
    card = r.json()
    assert "skills" in card
    assert any(s["id"] == "finance" for s in card["skills"])


def test_adjust_trust(client):
    r = client.post("/api/agents", json={"name": "X", "role": "headhunter"})
    aid = r.json()["agent_id"]
    r = client.post(f"/api/agents/{aid}/trust", json={"delta": 0.2, "reason": "good"})
    assert r.status_code == 200
    assert r.json()["trust_score"] == pytest.approx(0.7)
    r = client.get(f"/api/agents/{aid}/trust/history")
    assert r.status_code == 200
    assert len(r.json()) == 1


# ============ Tasks ============
def test_create_and_complete_task(client):
    r = client.post("/api/tasks", json={
        "kind": "test", "payload": {"x": 1},
    })
    assert r.status_code == 201
    tid = r.json()["task_id"]
    assert r.json()["state"] == "submitted"
    r = client.post(f"/api/tasks/{tid}/complete", params={"result": {"ok": True}})
    assert r.status_code == 200
    assert r.json()["state"] == "completed"


def test_task_state_filter(client):
    client.post("/api/tasks", json={"kind": "a", "payload": {}})
    client.post("/api/tasks", json={"kind": "b", "payload": {}})
    r = client.get("/api/tasks")
    assert len(r.json()) == 2
    r = client.get("/api/tasks", params={"state": "submitted"})
    assert len(r.json()) == 2


# ============ Delegations ============
def test_full_delegation_flow(client, isolated_data):
    """端到端: 注册 A,B → 录入候选人 → A 委托 B → B 接受 → 标记入职"""
    a_id = client.post("/api/agents", json={"name": "A", "role": "headhunter"}).json()["agent_id"]
    b_id = client.post("/api/agents", json={"name": "B", "role": "headhunter"}).json()["agent_id"]
    # 录入候选人 (走域 service)
    from zhongjie.domain.factory import build_services
    _, cand_svc, _ = build_services("data")
    cand = cand_svc.submit({"candidate_name": "张三", "phone": "13800138000"}, owner_agent_id=a_id)

    r = client.post("/api/delegations", json={
        "from_agent_id": a_id, "to_agent_id": b_id,
        "candidate_ref": cand.id, "jd_context": "P7",
        "fee_split": [{"agent_id": a_id, "pct": 0.4}, {"agent_id": b_id, "pct": 0.6}],
    })
    assert r.status_code == 201
    deleg_id = r.json()["id"]
    assert r.json()["status"] == "pending"

    r = client.post(f"/api/delegations/{deleg_id}/accept", params={"actor": b_id})
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"

    # accepted → in_progress → placed
    ds = __import__("zhongjie.api.deps", fromlist=["get_delegation_service"]).get_delegation_service()
    ds.start_progress(deleg_id, actor=b_id)
    r = client.post(f"/api/delegations/{deleg_id}/place", params={"actor": b_id})
    assert r.status_code == 200
    assert r.json()["status"] == "placed"


def test_delegation_acl_violation(client, isolated_data):
    """非 owner 不能发起委托"""
    a_id = client.post("/api/agents", json={"name": "A", "role": "headhunter"}).json()["agent_id"]
    b_id = client.post("/api/agents", json={"name": "B", "role": "headhunter"}).json()["agent_id"]
    c_id = client.post("/api/agents", json={"name": "C", "role": "headhunter"}).json()["agent_id"]
    from zhongjie.domain.factory import build_services
    _, cand_svc, _ = build_services("data")
    cand = cand_svc.submit({"candidate_name": "X"}, owner_agent_id=a_id)
    r = client.post("/api/delegations", json={
        "from_agent_id": c_id, "to_agent_id": b_id,
        "candidate_ref": cand.id,
    })
    assert r.status_code == 403


# ============ Billing ============
def test_create_and_settle_invoice(client):
    r = client.post("/api/billing/invoices", json={
        "delegation_id": "deleg_test",
        "candidate_ref": "cand_test",
        "total_amount": 100000,
        "fee_split": [
            {"agent_id": "hh-A", "pct": 0.4},
            {"agent_id": "hh-B", "pct": 0.5},
            {"agent_id": "platform", "pct": 0.1},
        ],
    })
    assert r.status_code == 201
    inv_id = r.json()["id"]
    assert r.json()["total_amount"] == 100000
    r = client.post(f"/api/billing/invoices/{inv_id}/settle")
    assert r.status_code == 200
    assert r.json()["status"] == "settled"


def test_invoice_split_amounts(client):
    r = client.post("/api/billing/invoices", json={
        "delegation_id": "d1", "candidate_ref": "c1",
        "total_amount": 10000,
        "fee_split": [
            {"agent_id": "hh-A", "pct": 0.7},
            {"agent_id": "hh-B", "pct": 0.3},
        ],
    })
    lines = {l["agent_id"]: l["amount"] for l in r.json()["lines"]}
    assert lines["hh-A"] == 7000.0
    assert lines["hh-B"] == 3000.0


def test_agent_billing_summary(client):
    client.post("/api/billing/invoices", json={
        "delegation_id": "d1", "candidate_ref": "c1",
        "total_amount": 10000,
        "fee_split": [{"agent_id": "hh-A", "pct": 1.0}],
    })
    r = client.get("/api/billing/agents/hh-A/summary")
    assert r.json()["total_pending"] == 10000.0
    assert r.json()["total_paid"] == 0.0


# ============ Audit ============
def test_audit_log_and_verify(client, isolated_data):
    from zhongjie.governance.audit import AppendOnlyAuditLog, AuditEntry
    import uuid
    log = AppendOnlyAuditLog(data_dir="data")
    entry = AuditEntry(
        id=f"aud_{uuid.uuid4().hex[:8]}",
        request_id="req_test", owner_agent_id="hh-A",
        decision="auto_approved_via_trust", matched_rule=None,
        trust_score=0.9, timestamp="2026-06-15T10:00:00",
    )
    log.append(entry)

    r = client.get("/api/audit")
    assert r.status_code == 200
    assert len(r.json()) >= 1

    r = client.get("/api/audit/verify")
    assert r.json()["is_valid"] is True


def test_audit_filter_by_agent(client, isolated_data):
    from zhongjie.governance.audit import AppendOnlyAuditLog, AuditEntry
    import uuid
    log = AppendOnlyAuditLog(data_dir="data")
    for i, agent in enumerate(["hh-A", "hh-B", "hh-A"]):
        log.append(AuditEntry(
            id=f"aud_{uuid.uuid4().hex[:8]}_{i}",
            request_id=f"req_{i}", owner_agent_id=agent,
            decision="rule_match", matched_rule=None,
            trust_score=0.5, timestamp="2026-06-15T10:00:00",
        ))
    r = client.get("/api/audit", params={"agent_id": "hh-A"})
    assert all(e["owner_agent_id"] == "hh-A" for e in r.json())


# ============ A2A ============
def test_a2a_tasks_send_via_http(client):
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "1",
        "method": "tasks/send",
        "params": {"message": {"parts": [{"type": "data", "data": {"skill": "delegate"}}]}},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert "result" in body


def test_a2a_well_known_card(client):
    r = client.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    card = r.json()
    assert "skills" in card
    assert any(s["id"] == "delegate" for s in card["skills"])
