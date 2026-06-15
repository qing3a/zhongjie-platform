"""
M3 单元测试 - 验证治理层独立可用 + 与老 p0_core.py 行为一致
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.governance.conditions import Condition
from zhongjie.governance.engine import RuleEngine
from zhongjie.governance.models import ActionType, Request, RequestStatus
from zhongjie.governance.rules import Rule


def test_condition_basic_ops():
    """Condition 7 种操作符全部正确"""
    req = Request(
        source="猎头_skill", target="甲方_skill", intent="test",
        payload={"amount": 500, "level": "P6", "tags": ["python", "fastapi"]},
    )
    # ==
    assert Condition("payload.amount", "==", 500).match(req)
    assert not Condition("payload.amount", "==", 600).match(req)
    # !=
    assert Condition("payload.amount", "!=", 600).match(req)
    # > <
    assert Condition("payload.amount", "<", 1000).match(req)
    assert not Condition("payload.amount", ">", 1000).match(req)
    # in
    assert Condition("source", "in", ["猎头_skill", "HR_skill"]).match(req)
    # not_in
    assert Condition("source", "not_in", ["unknown"]).match(req)
    # contains
    assert Condition("source", "contains", "猎头").match(req)


def test_condition_nested_field():
    """嵌套字段路径: payload.jd.level"""
    req = Request(
        source="猎头_skill", target="甲方_skill", intent="test",
        payload={"jd": {"level": "C-Level"}},
    )
    c = Condition("payload.jd.level", "==", "C-Level")
    assert c.match(req)


def test_rule_match_all_conditions():
    """Rule: 所有 conditions 命中才 match"""
    rule = Rule(
        id="r1", name="测试规则",
        conditions=[
            Condition("source", "==", "猎头_skill"),
            Condition("payload.amount", "<", 1000),
        ],
        action=ActionType.AUTO_APPROVE, priority=10,
    )
    # 全部满足
    req = Request(source="猎头_skill", target="甲方_skill", intent="t", payload={"amount": 500})
    assert rule.match(req)
    # 部分不满足
    req2 = Request(source="猎头_skill", target="甲方_skill", intent="t", payload={"amount": 5000})
    assert not rule.match(req2)


def test_engine_priority_order():
    """RuleEngine: 高优先级规则先命中"""
    engine = RuleEngine()
    # 优先级 30：黑名单拒绝
    engine.add_rule(Rule(
        id="r_blacklist", name="黑名单",
        conditions=[Condition("source", "in", ["bad_skill"])],
        action=ActionType.AUTO_REJECT, priority=30,
    ))
    # 优先级 10：小额自动通过
    engine.add_rule(Rule(
        id="r_small", name="小额",
        conditions=[Condition("payload.amount", "<", 1000)],
        action=ActionType.AUTO_APPROVE, priority=10,
    ))
    # 测试：黑名单应该被命中（即使也满足小额）
    req = Request(source="bad_skill", target="x", intent="t", payload={"amount": 500})
    result = engine.process(req)
    assert result["matched_rule"] == "r_blacklist"
    assert result["action"] == "auto_reject"
    assert req.status == RequestStatus.REJECTED


def test_engine_manual_review_goes_to_approval_desk():
    """manual_review → 入待审批队列 + 状态 PENDING"""
    engine = RuleEngine()
    engine.add_rule(Rule(
        id="r_review", name="C-Level 需审批",
        conditions=[Condition("payload.level", "==", "C-Level")],
        action=ActionType.MANUAL_REVIEW, priority=20,
    ))
    req = Request(source="猎头_skill", target="甲方_skill", intent="t",
                  payload={"level": "C-Level"})
    result = engine.process(req)
    assert result["action"] == "manual_review"
    assert req.status == RequestStatus.PENDING
    assert engine.approval_desk.find(req.id) is not None


def test_engine_default_is_manual_review():
    """未命中任何规则 → 默认 manual_review"""
    engine = RuleEngine()  # 空规则
    req = Request(source="猎头_skill", target="甲方_skill", intent="t", payload={})
    result = engine.process(req)
    assert result["action"] == "manual_review"
    assert result["matched_rule"] is None


def test_approval_desk_approve_reject():
    """审批台: approve/reject 修改状态 + 记录历史"""
    engine = RuleEngine()
    engine.add_rule(Rule(
        id="r1", name="review",
        conditions=[Condition("payload.amount", ">", 1000)],
        action=ActionType.MANUAL_REVIEW, priority=10,
    ))
    req = Request(source="x", target="y", intent="t", payload={"amount": 5000})
    engine.process(req)

    # approve
    assert engine.approve(req.id, decided_by="alice", comment="ok")
    assert req.status == RequestStatus.APPROVED
    assert engine.approval_desk.find(req.id) is None
    history = engine.approval_desk.history()
    assert len(history) == 1
    assert history[0].decided_by == "alice"
    assert history[0].decision.value == "approved"

    # reject 走一个新请求
    req2 = Request(source="x", target="y", intent="t", payload={"amount": 5000})
    engine.process(req2)
    assert engine.reject(req2.id, decided_by="bob", comment="no")
    assert req2.status == RequestStatus.REJECTED


def test_engine_thread_safe():
    """并发入队不重复"""
    import threading
    engine = RuleEngine()
    engine.add_rule(Rule(
        id="r1", name="review",
        conditions=[Condition("payload.amount", ">", 1000)],
        action=ActionType.MANUAL_REVIEW, priority=10,
    ))
    def submit_many():
        for _ in range(50):
            req = Request(source="x", target="y", intent="t", payload={"amount": 5000})
            engine.process(req)
    threads = [threading.Thread(target=submit_many) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    # 4 个线程 × 50 = 200 条入队
    assert len(engine.list_pending()) == 200


def test_request_serialization_compatible():
    """Request.to_dict() / from_dict() 与老 p0_core.py 字段一致"""
    req = Request(source="猎头_skill", target="甲方_skill", intent="test", payload={})
    d = req.to_dict()
    # 老格式必含字段
    assert all(k in d for k in ["id", "source", "target", "intent", "payload", "metadata", "status", "created_at"])
    assert d["status"] == "pending"  # 枚举→字符串

    # 反向解析
    req2 = Request.from_dict(d)
    assert req2.id == req.id
    assert req2.status == RequestStatus.PENDING
