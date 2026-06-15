"""
P3 M17 测试 - Agent Card 服务
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.identity.agent_card import AgentCard, AgentRole
from zhongjie.identity.registry import AgentRegistry
from zhongjie.protocol.agent_card_service import AgentCardService


@pytest.fixture
def service(tmp_path):
    reg = AgentRegistry(data_dir=tmp_path)
    return AgentCardService(reg)


def test_platform_card(service):
    """平台 Agent Card 总是可用"""
    card = service.platform_card()
    assert "name" in card
    assert "skills" in card
    assert any(s["id"] == "delegate" for s in card["skills"])
    assert card["authentication"]["schemes"] == ["bearer"]


def test_get_card_returns_a2a_format(service):
    a = AgentCard(name="hh-A", role=AgentRole.HEADHUNTER,
                  capabilities=["finance"], trust_score=0.8)
    service.registry.register(a)
    card = service.get_card(a.agent_id)
    assert card is not None
    assert card["name"] == "hh-A"
    assert card["metadata"]["role"] == "headhunter"
    assert card["metadata"]["trust_score"] == 0.8
    assert any(s["id"] == "finance" for s in card["skills"])


def test_get_card_unknown_returns_none(service):
    assert service.get_card("agent_fake") is None


def test_get_card_inactive_returns_none(service):
    a = AgentCard(name="X", role=AgentRole.HEADHUNTER)
    service.registry.register(a)
    service.registry.suspend(a.agent_id)
    assert service.get_card(a.agent_id) is None


def test_list_cards_all(service):
    for i in range(3):
        service.registry.register(AgentCard(name=f"X{i}", role=AgentRole.HEADHUNTER))
    assert len(service.list_cards()) == 3


def test_list_cards_by_role(service):
    service.registry.register(AgentCard(name="H1", role=AgentRole.HEADHUNTER))
    service.registry.register(AgentCard(name="E1", role=AgentRole.EMPLOYER))
    service.registry.register(AgentCard(name="H2", role=AgentRole.HEADHUNTER))
    hhs = service.list_cards(role=AgentRole.HEADHUNTER)
    assert len(hhs) == 2
    emps = service.list_cards(role=AgentRole.EMPLOYER)
    assert len(emps) == 1


def test_list_cards_by_capability(service):
    service.registry.register(AgentCard(name="A", role=AgentRole.HEADHUNTER,
                                          capabilities=["finance", "tech"]))
    service.registry.register(AgentCard(name="B", role=AgentRole.HEADHUNTER,
                                          capabilities=["tech"]))
    service.registry.register(AgentCard(name="C", role=AgentRole.HEADHUNTER,
                                          capabilities=["finance"]))
    finance_cards = service.list_cards(capability="finance")
    assert len(finance_cards) == 2
    assert {c["name"] for c in finance_cards} == {"A", "C"}


def test_list_cards_only_active(service):
    a1 = AgentCard(name="A1", role=AgentRole.HEADHUNTER)
    a2 = AgentCard(name="A2", role=AgentRole.HEADHUNTER)
    service.registry.register(a1)
    service.registry.register(a2)
    service.registry.suspend(a2.agent_id)
    assert len(service.list_cards()) == 1  # only active
    assert len(service.list_cards(only_active=False)) == 2  # all


def test_stats(service):
    service.registry.register(AgentCard(name="H1", role=AgentRole.HEADHUNTER, trust_score=0.6))
    service.registry.register(AgentCard(name="H2", role=AgentRole.HEADHUNTER, trust_score=0.8))
    service.registry.register(AgentCard(name="E1", role=AgentRole.EMPLOYER, trust_score=0.5))
    stats = service.stats()
    assert stats["total"] == 3
    assert stats["active"] == 3
    assert stats["avg_trust_score"] == 0.633  # round(0.6333, 3)
    assert stats["by_role"]["headhunter"] == 2
    assert stats["by_role"]["employer"] == 1
    assert stats["by_role"]["platform"] == 0
