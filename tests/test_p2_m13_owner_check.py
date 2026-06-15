"""
P2 M13 测试 - 委托发起方检查（assert_owner / share_to / unshare）
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.domain.factory import build_services
from zhongjie.domain.services import (
    CandidateNotFoundError, CandidateService, OwnerMismatchError
)


@pytest.fixture
def services(tmp_path):
    jd_svc, cand_svc, _ = build_services(str(tmp_path))
    return jd_svc, cand_svc


def test_submit_records_provenance(services, tmp_path):
    """submit 时: 记录 created provenance"""
    _, cand_svc = services
    c = cand_svc.submit({"candidate_name": "张三", "phone": "13800138000"}, owner_agent_id="hh-A")
    assert len(c.provenance) == 1
    assert c.provenance[0]["action"] == "created"
    assert c.provenance[0]["actor_agent_id"] == "hh-A"


def test_assert_owner_passes(services):
    _, cand_svc = services
    c = cand_svc.submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    # 不抛异常
    got = cand_svc.assert_owner("hh-A", c.id)
    assert got.id == c.id


def test_assert_owner_mismatch_raises(services):
    _, cand_svc = services
    c = cand_svc.submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    with pytest.raises(OwnerMismatchError):
        cand_svc.assert_owner("hh-B", c.id)


def test_assert_owner_candidate_not_found_raises(services):
    _, cand_svc = services
    with pytest.raises(CandidateNotFoundError):
        cand_svc.assert_owner("hh-A", "cand_fake")


def test_share_to_success(services):
    _, cand_svc = services
    c = cand_svc.submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    success, err = cand_svc.share_to("hh-A", c.id, "hh-B", ref_id="d1")
    assert success is True
    assert err is None
    c_after = cand_svc.get(c.id)
    assert "hh-B" in c_after.shared_with
    # provenance 记录
    actions = [p["action"] for p in c_after.provenance]
    assert "shared" in actions


def test_share_to_not_owner_fails(services):
    _, cand_svc = services
    c = cand_svc.submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    success, err = cand_svc.share_to("hh-B", c.id, "hh-C")  # hh-B 不是 owner
    assert success is False
    assert err == "ERR_NOT_OWNER"
    # 状态未变
    c_after = cand_svc.get(c.id)
    assert "hh-C" not in c_after.shared_with


def test_share_to_self_fails(services):
    _, cand_svc = services
    c = cand_svc.submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    success, err = cand_svc.share_to("hh-A", c.id, "hh-A")
    assert success is False
    assert err == "ERR_SELF_SHARE"


def test_share_to_nonexistent_candidate_fails(services):
    _, cand_svc = services
    success, err = cand_svc.share_to("hh-A", "cand_fake", "hh-B")
    assert success is False
    assert err == "ERR_CANDIDATE_NOT_FOUND"


def test_unshare_success(services):
    _, cand_svc = services
    c = cand_svc.submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    cand_svc.share_to("hh-A", c.id, "hh-B")
    success, err = cand_svc.unshare("hh-A", c.id, "hh-B")
    assert success is True
    c_after = cand_svc.get(c.id)
    assert "hh-B" not in c_after.shared_with
    assert c_after.visibility == "private"  # 自动回退


def test_unshare_not_owner_fails(services):
    _, cand_svc = services
    c = cand_svc.submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    cand_svc.share_to("hh-A", c.id, "hh-B")
    success, err = cand_svc.unshare("hh-C", c.id, "hh-B")  # hh-C 不是 owner
    assert success is False
    assert err == "ERR_NOT_OWNER"


def test_share_to_persists(services):
    """分享操作持久化到磁盘"""
    _, cand_svc = services
    c = cand_svc.submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    cand_svc.share_to("hh-A", c.id, "hh-B")
    # 新 build → 重新加载
    from zhongjie.domain.factory import build_services
    _, cand_svc2, _ = build_services(str(services[0]._repo._persist_path.parent))
    c2 = cand_svc2.get(c.id)
    assert "hh-B" in c2.shared_with
