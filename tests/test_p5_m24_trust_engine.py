"""
P5 M24 测试 - TrustAwareEngine
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.governance.conditions import Condition
from zhongjie.governance.engine import RuleEngine
from zhongjie.governance.models import ActionType, Request, RequestStatus
from zhongjie.governance.rules import Rule
from zhongjie.governance.trust_aware_engine import TrustAwareEngine


def test_high_trust_auto_approves():
    """trust_score >= 0.85 → auto_approved_via_trust, 跳过规则"""
    inner = RuleEngine()
    # 加一个 manual_review 规则（不期望命中）
    inner.add_rule(Rule(id="r1", name="需审批",
        conditions=[Condition("payload.amount", ">", 10000)],
        action=ActionType.MANUAL_REVIEW, priority=10))

    eng = TrustAwareEngine(rule_engine=inner)
    req = Request(source="hh-A", target="emp", intent="t",
                  payload={"amount": 50000})
    result = eng.process(req, owner_agent_id="hh-A", trust_score=0.9)
    assert result["action"] == "auto_approve"
    assert req.status == RequestStatus.APPROVED
    # 决策记录
    assert eng.history()[0].decision == "auto_approved_via_trust"


def test_low_trust_forces_manual_review():
    """trust_score <= 0.30 → 强制 manual_review"""
    inner = RuleEngine()
    # 加一个会 auto_approve 的规则（不期望命中）
    inner.add_rule(Rule(id="r1", name="小额通过",
        conditions=[Condition("payload.amount", "<", 1000)],
        action=ActionType.AUTO_APPROVE, priority=10))

    eng = TrustAwareEngine(rule_engine=inner)
    req = Request(source="hh-X", target="emp", intent="t",
                  payload={"amount": 100})  # 规则会批准
    result = eng.process(req, owner_agent_id="hh-X", trust_score=0.2)
    assert result["action"] == "manual_review"
    assert req.status == RequestStatus.PENDING
    assert eng.history()[0].decision == "manual_review_via_trust"


def test_medium_trust_uses_rule_engine():
    """0.30 < trust_score < 0.85 → 走规则引擎"""
    inner = RuleEngine()
    inner.add_rule(Rule(id="r1", name="小额通过",
        conditions=[Condition("payload.amount", "<", 1000)],
        action=ActionType.AUTO_APPROVE, priority=10))

    eng = TrustAwareEngine(rule_engine=inner)
    req = Request(source="hh-M", target="emp", intent="t", payload={"amount": 100})
    result = eng.process(req, owner_agent_id="hh-M", trust_score=0.5)
    assert result["action"] == "auto_approve"
    assert req.status == RequestStatus.APPROVED
    # 决策: 走规则
    assert eng.history()[0].decision == "rule_match"
    assert eng.history()[0].trust_skip_applied is False


def test_no_trust_score_falls_through_to_engine():
    """未提供 trust_score: 直接走 RuleEngine"""
    inner = RuleEngine()
    inner.add_rule(Rule(id="r1", name="小额通过",
        conditions=[Condition("payload.amount", "<", 1000)],
        action=ActionType.AUTO_APPROVE, priority=10))

    eng = TrustAwareEngine(rule_engine=inner)
    req = Request(source="hh-X", target="emp", intent="t", payload={"amount": 100})
    result = eng.process(req, owner_agent_id="hh-X")  # 无 trust_score
    assert result["action"] == "auto_approve"


def test_custom_thresholds():
    """自定义阈值"""
    eng = TrustAwareEngine(high_trust=0.95, low_trust=0.10)
    # 0.9 在 0.10~0.95 之间, 应走规则
    inner = RuleEngine()
    inner.add_rule(Rule(id="r1", name="小额",
        conditions=[Condition("payload.amount", "<", 1000)],
        action=ActionType.AUTO_APPROVE, priority=10))
    eng._engine = inner

    req = Request(source="hh-X", target="emp", intent="t", payload={"amount": 100})
    result = eng.process(req, trust_score=0.9)
    assert result["action"] == "auto_approve"  # 走规则


def test_decision_history():
    """决策历史可查"""
    eng = TrustAwareEngine()
    for ts in [0.9, 0.5, 0.1, 0.7]:
        req = Request(source="hh-X", target="emp", intent="t", payload={})
        eng.process(req, trust_score=ts)
    history = eng.history()
    assert len(history) == 4
    decisions = [d.decision for d in history]
    assert "auto_approved_via_trust" in decisions
    assert "manual_review_via_trust" in decisions
    assert decisions.count("rule_match") == 2


def test_history_filter_by_agent():
    eng = TrustAwareEngine()
    eng.process(Request(source="x", target="y", intent="t", payload={}), trust_score=0.9, owner_agent_id="hh-A")
    eng.process(Request(source="x", target="y", intent="t", payload={}), trust_score=0.1, owner_agent_id="hh-B")
    a_hist = eng.history("hh-A")
    b_hist = eng.history("hh-B")
    assert len(a_hist) == 1
    assert len(b_hist) == 1
    assert a_hist[0].decision == "auto_approved_via_trust"
    assert b_hist[0].decision == "manual_review_via_trust"


def test_stats():
    eng = TrustAwareEngine()
    for ts in [0.9, 0.5, 0.1, 0.7]:
        eng.process(Request(source="x", target="y", intent="t", payload={}), trust_score=ts)
    stats = eng.stats()
    assert stats["total"] == 4
    assert stats["by_decision"]["auto_approved_via_trust"] == 1
    assert stats["by_decision"]["manual_review_via_trust"] == 1
    assert stats["by_decision"]["rule_match"] == 2
    assert stats["trust_skip_rate"] == 0.5  # 2/4
