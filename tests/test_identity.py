"""
M6 单元测试 - AgentCard 模型
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.identity.agent_card import (
    AgentCard, AgentRole, AgentStatus, AgentTier
)


def test_agent_card_minimal_creation():
    """最简构造: agent_id 和 created_at 自动生成"""
    card = AgentCard(name="测试猎头", role=AgentRole.HEADHUNTER)
    assert card.agent_id.startswith("agent_")
    assert card.role == AgentRole.HEADHUNTER
    assert card.tier == AgentTier.STANDARD
    assert card.trust_score == 0.5
    assert card.status == AgentStatus.ACTIVE
    assert card.is_active()


def test_agent_card_with_all_fields():
    card = AgentCard(
        name="智联猎头-AI",
        role=AgentRole.HEADHUNTER,
        capabilities=["candidate_sourcing", "finance", "jd_matching"],
        tier=AgentTier.GOLD,
        trust_score=0.85,
        endpoint="https://hh-a.example.com/a2a",
        description="专注中高端金融岗",
    )
    assert card.can("finance")
    assert not card.can("manufacturing")
    assert card.tier == AgentTier.GOLD


def test_trust_score_bounds():
    """trust_score 越界校验"""
    import pytest
    with pytest.raises(ValueError):
        AgentCard(name="X", role=AgentRole.HEADHUNTER, trust_score=1.5)
    with pytest.raises(ValueError):
        AgentCard(name="X", role=AgentRole.HEADHUNTER, trust_score=-0.1)


def test_update_trust_clamps():
    card = AgentCard(name="X", role=AgentRole.HEADHUNTER, trust_score=0.5)
    assert card.update_trust(0.3) == pytest.approx(0.8)
    assert card.update_trust(0.5) == 1.0  # 钳到 1.0
    assert card.update_trust(-0.7) == pytest.approx(0.3)
    assert card.update_trust(-0.5) == 0.0  # 钳到 0.0


def test_status_transitions():
    card = AgentCard(name="X", role=AgentRole.HEADHUNTER)
    card.suspend()
    assert card.status == AgentStatus.SUSPENDED
    assert not card.is_active()
    card.activate()
    assert card.is_active()
    card.revoke()
    assert card.status == AgentStatus.REVOKED
    assert not card.is_active()


def test_to_dict_and_from_dict_round_trip():
    card = AgentCard(
        name="测试", role=AgentRole.HEADHUNTER,
        capabilities=["a", "b"], tier=AgentTier.SILVER, trust_score=0.7,
    )
    d = card.to_dict()
    assert d["role"] == "headhunter"
    assert d["tier"] == "silver"
    assert d["capabilities"] == ["a", "b"]

    card2 = AgentCard.from_dict(d)
    assert card2.agent_id == card.agent_id
    assert card2.role == AgentRole.HEADHUNTER
    assert card2.tier == AgentTier.SILVER
    assert card2.capabilities == ["a", "b"]


def test_from_dict_legacy_data():
    """兼容老数据: 缺字段用默认值"""
    legacy = {
        "agent_id": "agent_old", "name": "legacy", "role": "headhunter",
        # 缺: capabilities, tier, trust_score, status, created_at
    }
    card = AgentCard.from_dict(legacy)
    assert card.agent_id == "agent_old"
    assert card.capabilities == []
    assert card.trust_score == 0.5


def test_to_a2a_card_shape():
    """导出 A2A Protocol Agent Card 格式"""
    card = AgentCard(
        name="智联猎头-AI", role=AgentRole.HEADHUNTER,
        capabilities=["finance", "jd_matching"],
        trust_score=0.9, endpoint="https://x.com/a2a",
    )
    a2a = card.to_a2a_card()
    # A2A 必需字段
    assert a2a["name"] == "智联猎头-AI"
    assert "version" in a2a
    assert "capabilities" in a2a
    assert "skills" in a2a
    assert len(a2a["skills"]) == 2  # 每个 capability 一个 skill
    assert a2a["authentication"]["schemes"] == ["bearer"]
    # 平台扩展字段
    assert a2a["metadata"]["agent_id"] == card.agent_id
    assert a2a["metadata"]["role"] == "headhunter"
    assert a2a["metadata"]["trust_score"] == 0.9


def test_multiple_roles_supported():
    """三种角色都能正确建模"""
    h = AgentCard(name="猎头A", role=AgentRole.HEADHUNTER)
    e = AgentCard(name="甲方B", role=AgentRole.EMPLOYER)
    p = AgentCard(name="平台", role=AgentRole.PLATFORM)
    assert h.role.value == "headhunter"
    assert e.role.value == "employer"
    assert p.role.value == "platform"
