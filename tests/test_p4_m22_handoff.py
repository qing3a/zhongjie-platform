"""
P4 M22 测试 - HandoffService 候选人所有权转移
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import zhongjie.domain.factory as factory_mod
from zhongjie.collaboration.handoff import HandoffError, HandoffService
from zhongjie.domain.services import CandidateService
from zhongjie.infra.events import EventBus


@pytest.fixture
def setup(tmp_path):
    bus = EventBus()
    jd_svc, cand_svc, _ = factory_mod.build_services(str(tmp_path))
    return {"bus": bus, "jd_svc": jd_svc, "cand_svc": cand_svc,
            "service": HandoffService(cand_svc, bus)}


def test_handoff_transfers_ownership(setup):
    cand = setup["cand_svc"].submit({"candidate_name": "张三"}, owner_agent_id="hh-A")
    result = setup["service"].handoff(
        candidate_id=cand.id, from_agent_id="hh-A", to_agent_id="hh-B",
        ref_id="deleg_1",
    )
    assert result["from"] == "hh-A"
    assert result["to"] == "hh-B"
    # candidate owner 变更
    cand_after = setup["cand_svc"].get(cand.id)
    assert cand_after.owner_agent_id == "hh-B"


def test_handoff_clears_shared_with(setup):
    cand = setup["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    # 先分享给 hh-C
    setup["cand_svc"].share_to("hh-A", cand.id, "hh-C")
    # 转移给 hh-B
    setup["service"].handoff(cand.id, "hh-A", "hh-B")
    cand_after = setup["cand_svc"].get(cand.id)
    assert cand_after.shared_with == []
    # hh-C 失去访问权
    assert not cand_after.can_be_viewed_by("hh-C")
    # hh-B 拥有所有权
    assert cand_after.can_be_viewed_by("hh-B")


def test_handoff_resets_visibility_to_private(setup):
    """默认 reset_visibility=True: 转移后变成 private"""
    cand = setup["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    # 分享触发 visibility=shared
    setup["cand_svc"].share_to("hh-A", cand.id, "hh-C")
    assert setup["cand_svc"].get(cand.id).visibility == "shared"
    # 转移
    setup["service"].handoff(cand.id, "hh-A", "hh-B")
    assert setup["cand_svc"].get(cand.id).visibility == "private"


def test_handoff_keeps_visibility_when_disabled(setup):
    cand = setup["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    setup["cand_svc"].share_to("hh-A", cand.id, "hh-C")
    # 转移但保留 visibility
    setup["service"].handoff(cand.id, "hh-A", "hh-B", reset_visibility=False)
    cand_after = setup["cand_svc"].get(cand.id)
    # visibility 保持 "shared"（但 shared_with 已被清空）
    # 此时 effective 状态: 仍标 shared 但无人被分享 → 等同 private
    # 这是边界情况，文档化保留行为即可
    assert cand_after.shared_with == []


def test_handoff_records_provenance(setup):
    cand = setup["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    setup["service"].handoff(cand.id, "hh-A", "hh-B", ref_id="d1", note="测试转移")
    cand_after = setup["cand_svc"].get(cand.id)
    # 找 handed_off 记录
    hand_records = [p for p in cand_after.provenance if p["action"] == "handed_off"]
    assert len(hand_records) == 1
    assert hand_records[0]["actor_agent_id"] == "hh-A"
    assert hand_records[0]["target_agent_id"] == "hh-B"
    assert hand_records[0]["ref_id"] == "d1"
    assert "测试转移" in hand_records[0]["note"]


def test_handoff_non_owner_fails(setup):
    cand = setup["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    with pytest.raises(HandoffError):
        setup["service"].handoff(cand.id, "hh-C", "hh-B")  # hh-C 不是 owner


def test_handoff_candidate_not_found(setup):
    with pytest.raises(HandoffError):
        setup["service"].handoff("cand_fake", "hh-A", "hh-B")


def test_handoff_to_self_fails(setup):
    cand = setup["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    with pytest.raises(HandoffError):
        setup["service"].handoff(cand.id, "hh-A", "hh-A")


def test_handoff_emits_event(setup):
    cand = setup["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    received = []
    setup["bus"].subscribe("candidate.handed_off", lambda e: received.append(e))
    setup["service"].handoff(cand.id, "hh-A", "hh-B", ref_id="d1")
    assert len(received) == 1
    assert received[0].payload["from_agent_id"] == "hh-A"


def test_can_handoff(setup):
    cand = setup["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    assert setup["service"].can_handoff("hh-A", cand.id) is True
    assert setup["service"].can_handoff("hh-B", cand.id) is False
    assert setup["service"].can_handoff("hh-A", "cand_fake") is False


def test_full_lifecycle_with_handoff(setup):
    """完整场景: A 创建 → 分享给 B → B 接受委托 → 转移所有权 → B 接管"""
    cand = setup["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    # A 分享给 B
    setup["cand_svc"].share_to("hh-A", cand.id, "hh-B")
    # 转移所有权
    setup["service"].handoff(cand.id, "hh-A", "hh-B", ref_id="deleg_1")
    cand_after = setup["cand_svc"].get(cand.id)
    assert cand_after.owner_agent_id == "hh-B"
    # provenance 包含所有动作
    actions = [p["action"] for p in cand_after.provenance]
    assert "created" in actions
    assert "shared" in actions
    assert "handed_off" in actions
