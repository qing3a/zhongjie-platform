"""
P5 M23 测试 - TrustStrategy
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.identity.agent_card import AgentCard, AgentRole
from zhongjie.identity.registry import AgentRegistry
from zhongjie.identity.trust_strategy import DEFAULT_POLICIES, TrustStrategy
from zhongjie.infra.events import EventBus


@pytest.fixture
def stack(tmp_path):
    reg = AgentRegistry(data_dir=tmp_path)
    bus = EventBus()
    strategy = TrustStrategy(reg, bus)
    a1 = AgentCard(name="hh-A", role=AgentRole.HEADHUNTER, trust_score=0.5)
    a2 = AgentCard(name="hh-B", role=AgentRole.HEADHUNTER, trust_score=0.5)
    reg.register(a1)
    reg.register(a2)
    return {"reg": reg, "bus": bus, "strategy": strategy, "a1": a1, "a2": a2}


def test_default_policies_keys(stack):
    """默认策略覆盖关键事件"""
    assert "delegation.placed" in DEFAULT_POLICIES
    assert "task.failed" in DEFAULT_POLICIES


def test_delegation_placed_increases_trust(stack):
    """delegation.placed → from +0.1, to +0.2"""
    bus, strategy, a1, a2 = stack["bus"], stack["strategy"], stack["a1"], stack["a2"]
    bus.emit("delegation.placed", {
        "from_agent_id": a1.agent_id,
        "to_agent_id": a2.agent_id,
    })
    a1_after = stack["reg"].get(a1.agent_id)
    a2_after = stack["reg"].get(a2.agent_id)
    assert a1_after.trust_score == pytest.approx(0.6)
    assert a2_after.trust_score == pytest.approx(0.7)


def test_delegation_accepted_increases_trust(stack):
    stack["bus"].emit("delegation.accepted", {"to_agent_id": stack["a2"].agent_id})
    a2 = stack["reg"].get(stack["a2"].agent_id)
    assert a2.trust_score == pytest.approx(0.55)


def test_task_completed_increases_trust(stack):
    stack["bus"].emit("task.completed", {"owner_agent_id": stack["a1"].agent_id})
    a1 = stack["reg"].get(stack["a1"].agent_id)
    assert a1.trust_score == pytest.approx(0.52)


def test_task_failed_decreases_trust(stack):
    stack["bus"].emit("task.failed", {"owner_agent_id": stack["a1"].agent_id})
    a1 = stack["reg"].get(stack["a1"].agent_id)
    assert a1.trust_score == pytest.approx(0.45)


def test_security_suspicious_large_penalty(stack):
    """security.suspicious → -0.20"""
    stack["bus"].emit("security.suspicious", {"actor": stack["a1"].agent_id})
    a1 = stack["reg"].get(stack["a1"].agent_id)
    assert a1.trust_score == pytest.approx(0.30)


def test_trust_clamped_to_bounds(stack):
    """调整后不越界"""
    # hh-A 起始 0.5
    # task.completed +0.02 * 多次
    for _ in range(50):  # 累加 +1.0
        stack["bus"].emit("task.completed", {"owner_agent_id": stack["a1"].agent_id})
    a1 = stack["reg"].get(stack["a1"].agent_id)
    assert a1.trust_score == 1.0  # 钳到 1.0


def test_unknown_event_ignored(stack):
    """未配置策略的事件: 不影响信任分"""
    initial = stack["reg"].get(stack["a1"].agent_id).trust_score
    stack["bus"].emit("unknown.event", {"actor": stack["a1"].agent_id})
    after = stack["reg"].get(stack["a1"].agent_id).trust_score
    assert after == initial


def test_history_recorded(stack):
    """每次调整都记入 history"""
    bus, strategy, a1, a2 = stack["bus"], stack["strategy"], stack["a1"], stack["a2"]
    bus.emit("task.completed", {"owner_agent_id": a1.agent_id})
    bus.emit("task.failed", {"owner_agent_id": a1.agent_id})
    bus.emit("delegation.placed", {"from_agent_id": a1.agent_id, "to_agent_id": a2.agent_id})
    # delegation.placed 触发两条 (from + to) → 4 条
    history = strategy.history()
    assert len(history) == 4
    deltas = [h["delta"] for h in history]
    assert deltas == [
        pytest.approx(0.02),   # task.completed → hh-A
        pytest.approx(-0.05),  # task.failed → hh-A
        pytest.approx(0.10),   # delegation.placed → hh-A (from)
        pytest.approx(0.20),   # delegation.placed → hh-B (to)
    ]


def test_history_filter_by_agent(stack):
    bus, a1, a2 = stack["bus"], stack["a1"], stack["a2"]
    stack["bus"].emit("task.completed", {"owner_agent_id": a1.agent_id})
    stack["bus"].emit("task.completed", {"owner_agent_id": a2.agent_id})
    a1_hist = stack["strategy"].history(a1.agent_id)
    a2_hist = stack["strategy"].history(a2.agent_id)
    assert len(a1_hist) == 1
    assert len(a2_hist) == 1


def test_manual_adjustment(stack):
    """手动调整不走事件"""
    initial = stack["reg"].get(stack["a1"].agent_id).trust_score
    new = stack["strategy"].apply_manual(stack["a1"].agent_id, 0.15, reason="test")
    assert new == pytest.approx(0.65)
    # history 中标记为 manual
    hist = stack["strategy"].history(stack["a1"].agent_id)
    assert any(h["event_type"] == "manual" for h in hist)


def test_custom_policy(stack):
    """加自定义策略"""
    stack["strategy"].add_policy("custom.event", "actor", 0.3)
    stack["bus"].emit("custom.event", {"actor": stack["a1"].agent_id})
    a1 = stack["reg"].get(stack["a1"].agent_id)
    assert a1.trust_score == pytest.approx(0.8)


def test_policy_for(stack):
    p = stack["strategy"].policy_for("delegation.placed")
    assert ("from_agent_id", 0.10) in p
    assert ("to_agent_id", 0.20) in p
