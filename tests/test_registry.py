"""
M7 单元测试 - AgentRegistry
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.identity.agent_card import AgentCard, AgentRole, AgentStatus, AgentTier
from zhongjie.identity.registry import AgentRegistry


def test_register_and_get(tmp_path):
    reg = AgentRegistry(data_dir=tmp_path)
    card = AgentCard(name="猎头A", role=AgentRole.HEADHUNTER,
                     capabilities=["finance"])
    reg.register(card)
    got = reg.get(card.agent_id)
    assert got is not None
    assert got.name == "猎头A"


def test_register_with_dict():
    """register() 接收 dict 自动转 AgentCard"""
    reg = AgentRegistry(data_dir="data")
    data = {
        "agent_id": "agent_test1", "name": "测试", "role": "headhunter",
        "capabilities": ["a"], "tier": "gold", "trust_score": 0.7,
        "status": "active",
    }
    card = reg.register(data)
    assert card.agent_id == "agent_test1"
    assert card.tier == AgentTier.GOLD


def test_list_by_role(tmp_path):
    reg = AgentRegistry(data_dir=tmp_path)
    reg.register(AgentCard(name="HH1", role=AgentRole.HEADHUNTER))
    reg.register(AgentCard(name="HH2", role=AgentRole.HEADHUNTER))
    reg.register(AgentCard(name="E1", role=AgentRole.EMPLOYER))
    hhs = reg.list_by_role(AgentRole.HEADHUNTER)
    emps = reg.list_by_role(AgentRole.EMPLOYER)
    assert len(hhs) == 2
    assert len(emps) == 1


def test_list_by_capability_filters_inactive(tmp_path):
    reg = AgentRegistry(data_dir=tmp_path)
    a1 = AgentCard(name="A1", role=AgentRole.HEADHUNTER, capabilities=["finance"])
    a2 = AgentCard(name="A2", role=AgentRole.HEADHUNTER, capabilities=["finance", "tech"])
    a3 = AgentCard(name="A3", role=AgentRole.HEADHUNTER, capabilities=["tech"])
    reg.register(a1)
    reg.register(a2)
    reg.register(a3)
    # 暂停 a2
    reg.suspend(a2.agent_id)
    finance_agents = reg.list_by_capability("finance")
    # 只有 a1 应该出现（a2 被 suspend）
    assert len(finance_agents) == 1
    assert finance_agents[0].agent_id == a1.agent_id


def test_status_transitions_persist(tmp_path):
    reg = AgentRegistry(data_dir=tmp_path)
    card = AgentCard(name="X", role=AgentRole.HEADHUNTER)
    reg.register(card)
    assert reg.suspend(card.agent_id)
    assert reg.get(card.agent_id).status == AgentStatus.SUSPENDED
    assert reg.activate(card.agent_id)
    assert reg.get(card.agent_id).status == AgentStatus.ACTIVE
    assert reg.revoke(card.agent_id)
    assert reg.get(card.agent_id).status == AgentStatus.REVOKED


def test_update_trust(tmp_path):
    reg = AgentRegistry(data_dir=tmp_path)
    card = AgentCard(name="X", role=AgentRole.HEADHUNTER, trust_score=0.5)
    reg.register(card)
    new_score = reg.update_trust(card.agent_id, 0.3)
    assert new_score == 0.8
    assert reg.get(card.agent_id).trust_score == 0.8
    # 不存在
    assert reg.update_trust("agent_fake", 0.1) is None


def test_persistence_across_instances(tmp_path):
    """持久化: 一个实例注册，另一个实例能加载"""
    reg1 = AgentRegistry(data_dir=tmp_path)
    card = AgentCard(name="持久化", role=AgentRole.HEADHUNTER,
                     capabilities=["test"])
    reg1.register(card)
    # 新实例
    reg2 = AgentRegistry(data_dir=tmp_path)
    assert reg2.has(card.agent_id)
    assert reg2.get(card.agent_id).name == "持久化"


def test_find_by_endpoint(tmp_path):
    reg = AgentRegistry(data_dir=tmp_path)
    c = AgentCard(name="X", role=AgentRole.HEADHUNTER, endpoint="https://x.com/a2a")
    reg.register(c)
    found = reg.find_by_endpoint("https://x.com/a2a")
    assert found is not None
    assert found.agent_id == c.agent_id


def test_count_and_list_all(tmp_path):
    reg = AgentRegistry(data_dir=tmp_path)
    assert reg.count() == 0
    for i in range(5):
        reg.register(AgentCard(name=f"A{i}", role=AgentRole.HEADHUNTER))
    assert reg.count() == 5
    assert len(reg.list_all()) == 5
