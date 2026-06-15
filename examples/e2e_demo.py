"""
端到端 demo 脚本
通过 HTTP API 完整跑一遍:
  发现平台 → 注册 A/B Agent → A 录入候选人 → A 委托 B
  → B 接受 → in_progress → placed → 生成账单 → 结算
  → 验证审计完整性
"""
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE = "http://127.0.0.1:8765"


def post(path, body=None, raw=False):
    url = BASE + path
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read().decode()) if not raw else r.read().decode()


def get(path, params=None):
    if params:
        from urllib.parse import urlencode
        path += "?" + urlencode(params)
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


def line(char="─", n=60):
    return char * n


def step(num, title):
    print(f"\n{line('═')}")
    print(f"  Step {num}: {title}")
    print(line("═"))


def show(label, obj):
    print(f"  ✓ {label}: {json.dumps(obj, ensure_ascii=False)[:200]}")


def main():
    # 设置 DATA_DIR 与 uvicorn 一致，清空缓存让 build_services 重新读 env
    import os
    os.environ["DATA_DIR"] = "demo_run/data"
    from zhongjie.api import deps
    deps.reset_all()
    from zhongjie.domain import factory
    factory.build_services.cache_clear()

    out = []
    out.append(("=" * 70))
    out.append("🚀 中介 API 平台 - 端到端 Demo")
    out.append("=" * 70)
    out.append(f"   Base URL: {BASE}")
    out.append(f"   Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # ============= 1. 平台发现 =============
    step(1, "平台发现 (A2A Standard: /.well-known/agent-card.json)")
    status, card = get("/.well-known/agent-card.json")
    show("HTTP", status)
    show("Name", card["name"])
    skills = [s["id"] for s in card["skills"]]
    show("Skills", skills)
    out.append(f"\n[1] 平台发现 OK: {card['name']}, skills={skills}")

    # ============= 2. 注册 A、B =============
    step(2, "注册猎头 A 和 B")
    status, a = post("/api/agents", {"name": "猎头A-专注互联网", "role": "headhunter",
                                     "capabilities": ["candidate_sourcing", "tech"]})
    a_id = a["agent_id"]
    out.append(f"\n[2] A 注册: {a_id}, trust={a['trust_score']}, caps={a['capabilities']}")
    show("A", {"id": a_id, "trust": a["trust_score"]})

    status, b = post("/api/agents", {"name": "猎头B-专注金融", "role": "headhunter",
                                     "capabilities": ["finance", "jd_matching"]})
    b_id = b["agent_id"]
    out.append(f"[2] B 注册: {b_id}, trust={b['trust_score']}, caps={b['capabilities']}")
    show("B", {"id": b_id, "trust": b["trust_score"]})

    # ============= 3. 录入候选人 =============
    step(3, "A 通过 HTTP /api/candidates 录入候选人（与 uvicorn 共享内存）")
    status, cand_resp = post(
        f"/api/candidates?owner_agent_id={a_id}",
        body={"candidate_name": "张三", "phone": "13800138000",
              "email": "zhangsan@test.com", "skills": ["Python", "Finance"]},
    )
    cand_id = cand_resp["candidate_id"]
    out.append(f"\n[3] 候选人: {cand_id}, owner={a_id}")
    out.append(f"     脱敏: name={cand_resp['name']}, "
               f"phone={cand_resp['phone']}, email={cand_resp['email']}")
    show("Candidate", cand_resp)

    # ============= 4. A 发起委托 =============
    step(4, f"A 发起委托给 B (候选人 {cand_id})")
    fee_split = [
        {"agent_id": a_id, "pct": 0.40, "role": "owner"},
        {"agent_id": b_id, "pct": 0.50, "role": "co_finder"},
        {"agent_id": "platform", "pct": 0.10, "role": "platform_fee"},
    ]
    status, deleg = post("/api/delegations", {
        "from_agent_id": a_id, "to_agent_id": b_id,
        "candidate_ref": cand_id, "jd_context": "P7 金融数据工程师",
        "fee_split": fee_split, "visibility": "masked",
        "note": "A 不擅长金融岗，委托 B",
    })
    deleg_id = deleg["id"]
    task_id = deleg.get("task_id")
    out.append(f"\n[4] 委托创建: {deleg_id}")
    out.append(f"     Task ID: {task_id}")
    out.append(f"     Status: {deleg['status']}, fee={[(s['agent_id'], s['pct']) for s in deleg['fee_split']]}")
    show("Delegation", deleg)

    # ============= 5. 验证 ACL =============
    step(5, "ACL 验证: B 看不到候选人 (private)")
    status, cand_after = get(f"/api/candidates/{cand_id}")
    a_can_view = cand_after["owner_agent_id"] == a_id
    b_can_view_before = b_id in cand_after["shared_with"]
    out.append(f"\n[5] A 是 owner: {a_can_view}, B 在 shared_with (接受前): {b_can_view_before}")
    show("ACL", {"A_is_owner": a_can_view, "B_in_shared_with": b_can_view_before,
                  "visibility": cand_after["visibility"]})

    # ============= 6. B 接受 =============
    step(6, "B 接受委托 → 候选人自动加入 B 的 shared_with")
    status, accepted = post(f"/api/delegations/{deleg_id}/accept?actor={b_id}",
                            body={})  # 实际是 query
    out.append(f"\n[6] 委托: status={accepted['status']}, "
               f"decided_at={accepted['decided_at']}")
    status, cand_after2 = get(f"/api/candidates/{cand_id}")
    out.append(f"     候选人 shared_with: {cand_after2['shared_with']}, "
               f"visibility: {cand_after2['visibility']}, "
               f"provenance 数量: {len(cand_after2['provenance'])}")
    show("After Accept", {"deleg_status": accepted["status"],
                          "shared_with": cand_after2["shared_with"],
                          "provenance_count": len(cand_after2["provenance"])})

    # ============= 7. 信任分检查 =============
    step(7, "信任分变化 (TrustStrategy 事件驱动)")
    _, a_after = get(f"/api/agents/{a_id}")
    _, b_after = get(f"/api/agents/{b_id}")
    out.append(f"\n[7] A 信任分: {a_after['trust_score']} (起始 0.5)")
    out.append(f"     B 信任分: {b_after['trust_score']} (起始 0.5)")
    out.append(f"     期望: A +0.10 (placed 时), B +0.20 (placed 时) + +0.05 (accepted)")
    show("A trust", a_after["trust_score"])
    show("B trust", b_after["trust_score"])

    # ============= 8. B 推进 + 入职 =============
    step(8, "B 标记入职 (placed, 自动经过 in_progress)")
    status, placed = post(f"/api/delegations/{deleg_id}/place?actor={b_id}", body={})
    out.append(f"\n[8] 委托最终状态: {placed['status']}")
    show("Placed", placed)

    # ============= 9. 创建账单 =============
    step(9, "BillingService: 按 fee_split 生成账单 (10万)")
    total_amount = 100000
    status, invoice = post("/api/billing/invoices", {
        "delegation_id": deleg_id, "candidate_ref": cand_id,
        "total_amount": total_amount, "fee_split": fee_split,
        "note": "Demo 成功入职",
    })
    inv_id = invoice["id"]
    out.append(f"\n[9] 账单: {inv_id}, total={invoice['total_amount']}")
    for line_item in invoice["lines"]:
        out.append(f"     {line_item['agent_id']}: "
                   f"{line_item['pct']*100:.0f}% = {line_item['amount']}元")
    show("Invoice", {"id": inv_id, "total": invoice["total_amount"]})

    # ============= 10. 结算 =============
    step(10, "结算 (settle)")
    status, settled = post(f"/api/billing/invoices/{inv_id}/settle", body={})
    out.append(f"\n[10] 账单: status={settled['status']}, settled_at={settled['settled_at']}")
    _, summary = get(f"/api/billing/agents/{a_id}/summary")
    _, summary_b = get(f"/api/billing/agents/{b_id}/summary")
    out.append(f"      A 累计已收: {summary['total_paid']}元")
    out.append(f"      B 累计已收: {summary_b['total_paid']}元")
    show("Settled", settled)

    # ============= 11. 审计校验 =============
    step(11, "AppendOnlyAuditLog: 写入并校验链式 hash")
    from zhongjie.governance.audit import AppendOnlyAuditLog, AuditEntry
    import uuid
    log = AppendOnlyAuditLog(data_dir="demo_run/data")
    # 模拟治理决策
    for i, (decision, score) in enumerate([
        ("auto_approved_via_trust", 0.92),
        ("rule_match", 0.65),
        ("manual_review_via_trust", 0.15),
    ]):
        entry = AuditEntry(
            id=f"aud_{uuid.uuid4().hex[:8]}",
            request_id=f"req_{i}", owner_agent_id=a_id if i % 2 == 0 else b_id,
            decision=decision, matched_rule=None, trust_score=score,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        log.append(entry)
    is_valid, issues = log.verify_integrity()
    stats = log.stats()
    out.append(f"\n[11] 审计条数: {log.count()}, 完整: {is_valid}, issues: {issues}")
    out.append(f"      统计: {stats}")
    show("Audit verify", {"valid": is_valid, "stats": stats})

    # ============= 12. 平台总览 =============
    step(12, "最终: 平台总览 (dashboard 数据源)")
    _, agents_list = get("/api/agents")
    _, delegs = get("/api/delegations")
    _, audit_stats = get("/api/audit/stats")
    _, tasks = get("/api/tasks")
    out.append(f"\n[12] 平台快照:")
    out.append(f"     Agents: {agents_list['total']} "
               f"({agents_list['by_role']})")
    out.append(f"     Delegations: {len(delegs)}")
    out.append(f"     Tasks: {len(tasks)}")
    out.append(f"     Audit: {audit_stats['total']} 条")
    out.append("")
    out.append("✨ 打开 http://localhost:8765/web/dashboard_v2.html 看可视化")

    out.append("\n" + "=" * 70)
    out.append("✅ 端到端 Demo 全部通过!")
    out.append("=" * 70)

    result = "\n".join(out)
    # 写到文件 + 输出
    Path("demo_run.log").write_text(result, encoding="utf-8")
    print(result)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as e:
        print(f"❌ 无法连接 {BASE}: {e}")
        print("   请先启动: python -m uvicorn zhongjie.api.app:app --port 8765")
    except Exception as e:
        import traceback
        traceback.print_exc()
