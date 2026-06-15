"""
P2 M10 测试 - Candidate 增强：provenance / share_to / unshare / can_be_viewed_by
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.domain.models import Candidate, Provenance, Visibility


def test_candidate_default_private():
    """默认 private 可见性，仅 owner 可看"""
    c = Candidate(id="c1", owner_agent_id="hh-A")
    assert c.visibility == "private"
    assert c.can_be_viewed_by("hh-A") is True
    assert c.can_be_viewed_by("hh-B") is False


def test_share_to_makes_shared_and_records_provenance():
    """share_to: 自动改 visibility + 记录 provenance"""
    c = Candidate(id="c1", owner_agent_id="hh-A")
    assert c.share_to("hh-B", actor_agent_id="hh-A", ref_id="deleg_1")
    assert c.visibility == "shared"
    assert "hh-B" in c.shared_with
    # provenance
    assert len(c.provenance) == 1
    assert c.provenance[0]["action"] == "shared"
    assert c.provenance[0]["actor_agent_id"] == "hh-A"
    assert c.provenance[0]["target_agent_id"] == "hh-B"
    assert c.provenance[0]["ref_id"] == "deleg_1"


def test_share_to_idempotent():
    """重复 share 同一 agent 不产生新 provenance"""
    c = Candidate(id="c1", owner_agent_id="hh-A")
    c.share_to("hh-B", actor_agent_id="hh-A")
    assert not c.share_to("hh-B", actor_agent_id="hh-A")
    assert len(c.provenance) == 1


def test_unshare_removes_and_may_revert_to_private():
    c = Candidate(id="c1", owner_agent_id="hh-A")
    c.share_to("hh-B", actor_agent_id="hh-A")
    c.share_to("hh-C", actor_agent_id="hh-A")
    assert c.unshare("hh-B")
    assert "hh-B" not in c.shared_with
    assert c.visibility == "shared"  # 还有 hh-C
    c.unshare("hh-C")
    assert c.visibility == "private"  # 自动回到 private


def test_acl_view_matrix():
    """ACL 视图矩阵:
    private: 仅 owner
    shared:  owner + shared_with
    public:  任何人
    """
    # private
    c1 = Candidate(id="c1", owner_agent_id="hh-A")
    assert c1.can_be_viewed_by("hh-A")
    assert not c1.can_be_viewed_by("hh-B")
    assert not c1.can_be_viewed_by("hh-C")

    # shared
    c2 = Candidate(id="c2", owner_agent_id="hh-A")
    c2.share_to("hh-B", actor_agent_id="hh-A")
    assert c2.can_be_viewed_by("hh-A")  # owner
    assert c2.can_be_viewed_by("hh-B")  # 分享了
    assert not c2.can_be_viewed_by("hh-C")  # 第三方

    # public
    c3 = Candidate(id="c3", owner_agent_id="hh-A", visibility="public")
    assert c3.can_be_viewed_by("hh-A")
    assert c3.can_be_viewed_by("hh-B")
    assert c3.can_be_viewed_by("anyone")


def test_add_provenance_chain():
    """多次操作形成完整来源链"""
    c = Candidate(id="c1", owner_agent_id="hh-A")
    c.add_provenance("created", actor_agent_id="hh-A", note="猎头A 录入")
    c.add_provenance("shared", actor_agent_id="hh-A", target_agent_id="hh-B")
    c.add_provenance("delegated", actor_agent_id="hh-B", target_agent_id="hh-C",
                     ref_id="deleg_42")
    assert len(c.provenance) == 3
    actions = [p["action"] for p in c.provenance]
    assert actions == ["created", "shared", "delegated"]
    # 验证 ref_id 链路
    assert c.provenance[2]["ref_id"] == "deleg_42"


def test_legacy_candidate_loads_with_provenance_default_empty():
    """老数据无 provenance 字段时默认为空列表"""
    legacy = {
        "id": "c1", "owner_agent_id": "hh-A",
        "candidate_name": "X", "visibility": "private",
        # 缺: provenance, shared_with
    }
    c = Candidate.from_dict(legacy)
    assert c.provenance == []
    assert c.shared_with == []


def test_candidate_round_trip_preserves_provenance():
    c = Candidate(id="c1", owner_agent_id="hh-A")
    c.share_to("hh-B", actor_agent_id="hh-A", ref_id="d1")
    c.add_provenance("contacted", actor_agent_id="hh-B", note="电话联系")
    d = c.to_dict()
    c2 = Candidate.from_dict(d)
    assert len(c2.provenance) == 2
    assert c2.shared_with == ["hh-B"]
    assert c2.visibility == "shared"


def test_visibility_enum_exists():
    """Visibility 枚举三类齐全"""
    assert Visibility.PRIVATE.value == "private"
    assert Visibility.SHARED.value == "shared"
    assert Visibility.PUBLIC.value == "public"
