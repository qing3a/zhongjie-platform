"""
P5 M25 测试 - 治理决策审计
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import uuid
from zhongjie.governance.audit import AppendOnlyAuditLog, AuditEntry


@pytest.fixture
def log(tmp_path):
    return AppendOnlyAuditLog(data_dir=tmp_path)


def make_entry(decision: str = "rule_match", agent: str = "hh-A",
               trust: float = 0.5, **kwargs) -> AuditEntry:
    return AuditEntry(
        id=f"aud_{uuid.uuid4().hex[:8]}",
        request_id=f"req_{uuid.uuid4().hex[:8]}",
        owner_agent_id=agent,
        decision=decision,
        matched_rule=kwargs.get("matched_rule", "rule_001"),
        trust_score=trust,
        timestamp=kwargs.get("timestamp", "2026-06-15T10:00:00"),
        note=kwargs.get("note", ""),
    )


def test_append_assigns_hash_and_prev(log):
    """append 自动算 hash 和 prev_hash"""
    e1 = make_entry(decision="auto_approved_via_trust")
    log.append(e1)
    assert e1.prev_hash == ""  # 第一条
    assert len(e1.hash) == 64   # sha256 hex

    e2 = make_entry(decision="manual_review_via_trust")
    log.append(e2)
    assert e2.prev_hash == e1.hash  # 链式


def test_verify_integrity_passes(log):
    """完整性校验通过"""
    for i in range(5):
        log.append(make_entry(decision="rule_match"))
    is_valid, issues = log.verify_integrity()
    assert is_valid
    assert issues == []


def test_verify_integrity_detects_tampering(log):
    """篡改后校验失败"""
    e1 = make_entry(decision="rule_match")
    e2 = make_entry(decision="auto_approved_via_trust")
    log.append(e1)
    log.append(e2)
    # 篡改 e1 的 decision
    e1.decision = "fake_decision"
    is_valid, issues = log.verify_integrity()
    assert not is_valid
    assert len(issues) >= 1


def test_by_agent(log):
    log.append(make_entry(agent="hh-A"))
    log.append(make_entry(agent="hh-B"))
    log.append(make_entry(agent="hh-A"))
    a = log.by_agent("hh-A")
    b = log.by_agent("hh-B")
    assert len(a) == 2
    assert len(b) == 1


def test_by_decision(log):
    log.append(make_entry(decision="auto_approved_via_trust"))
    log.append(make_entry(decision="manual_review_via_trust"))
    log.append(make_entry(decision="rule_match"))
    log.append(make_entry(decision="auto_approved_via_trust"))
    approved = log.by_decision("auto_approved_via_trust")
    assert len(approved) == 2


def test_by_trust_range(log):
    log.append(make_entry(trust=0.1))
    log.append(make_entry(trust=0.5))
    log.append(make_entry(trust=0.9))
    high = log.by_trust_range(high=1.0, low=0.7)
    mid = log.by_trust_range(high=0.7, low=0.3)
    low = log.by_trust_range(high=0.3, low=0.0)
    assert len(high) == 1
    assert len(mid) == 1
    assert len(low) == 1


def test_stats(log):
    for d, t in [
        ("auto_approved_via_trust", 0.9),
        ("manual_review_via_trust", 0.1),
        ("rule_match", 0.5),
        ("rule_match", 0.6),
    ]:
        log.append(make_entry(decision=d, trust=t))
    stats = log.stats()
    assert stats["total"] == 4
    assert stats["by_decision"]["rule_match"] == 2
    assert stats["trust_score"]["min"] == 0.1
    assert stats["trust_score"]["max"] == 0.9
    assert stats["trust_score"]["avg"] == pytest.approx(0.525)


def test_persistence(tmp_path):
    log1 = AppendOnlyAuditLog(data_dir=tmp_path)
    e1 = make_entry()
    log1.append(e1)

    log2 = AppendOnlyAuditLog(data_dir=tmp_path)
    assert log2.count() == 1
    e_loaded = log2.all()[0]
    assert e_loaded.id == e1.id
    # 持久化后 hash 应保持（链式 hash 还能验证）
    is_valid, _ = log2.verify_integrity()
    assert is_valid


def test_entry_dataclass_round_trip():
    e = make_entry()
    from dataclasses import asdict
    d = asdict(e)
    e2 = AuditEntry(**d)
    assert e2.id == e.id
    assert e2.decision == e.decision
