"""
P2 M12 测试 - AccessControl 服务
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.domain.models import Candidate, JD, Match
from zhongjie.governance.acl import AccessControl, PermissionError_


@pytest.fixture
def acl() -> AccessControl:
    return AccessControl(agent_roles={
        "admin1": "admin",
        "hh-A": "headhunter",
        "hh-B": "headhunter",
        "hh-C": "headhunter",
        "emp1": "employer",
    })


def test_platform_admin_can_view_anything(acl):
    c = Candidate(id="c1", owner_agent_id="hh-A")
    assert acl.can_view_candidate("admin1", c) is True
    assert acl.can_edit_candidate("admin1", c) is True


def test_owner_can_view_edit_their_own(acl):
    c = Candidate(id="c1", owner_agent_id="hh-A")
    assert acl.can_view_candidate("hh-A", c) is True
    assert acl.can_edit_candidate("hh-A", c) is True


def test_non_owner_cannot_view_private(acl):
    c = Candidate(id="c1", owner_agent_id="hh-A")  # private 默认
    assert acl.can_view_candidate("hh-B", c) is False
    assert acl.can_edit_candidate("hh-B", c) is False


def test_shared_agent_can_view(acl):
    c = Candidate(id="c1", owner_agent_id="hh-A")
    c.share_to("hh-B", actor_agent_id="hh-A")
    assert acl.can_view_candidate("hh-B", c) is True
    # 但 B 不能编辑
    assert acl.can_edit_candidate("hh-B", c) is False


def test_public_candidate_visible_to_everyone(acl):
    c = Candidate(id="c1", owner_agent_id="hh-A", visibility="public")
    assert acl.can_view_candidate("hh-B", c) is True
    assert acl.can_view_candidate("hh-C", c) is True
    assert acl.can_view_candidate("emp1", c) is True


def test_assert_can_view_raises_on_no_permission(acl):
    c = Candidate(id="c1", owner_agent_id="hh-A")
    with pytest.raises(PermissionError_):
        acl.assert_can_view_candidate("hh-B", c)


def test_assert_can_view_passes(acl):
    c = Candidate(id="c1", owner_agent_id="hh-A")
    acl.assert_can_view_candidate("hh-A", c)  # 不抛


def test_filter_visible_candidates(acl):
    cands = [
        Candidate(id="c1", owner_agent_id="hh-A"),  # private, A only
        Candidate(id="c2", owner_agent_id="hh-A", visibility="public"),
        Candidate(id="c3", owner_agent_id="hh-B"),  # private, B only
    ]
    # hh-B 能看的: c2 (public) + c3 (own)
    visible_to_B = acl.filter_visible_candidates("hh-B", cands)
    assert {c.id for c in visible_to_B} == {"c2", "c3"}
    # hh-A 能看的: c1 + c2
    visible_to_A = acl.filter_visible_candidates("hh-A", cands)
    assert {c.id for c in visible_to_A} == {"c1", "c2"}


def test_jd_acl_no_owner_public(acl):
    """JD 无 owner_agent_id 时：所有人可见"""
    jd = JD(id="jd1", jd_title="X")
    assert jd.owner_agent_id is None
    assert acl.can_view_jd("hh-A", jd)
    assert acl.can_view_jd("hh-B", jd)


def test_jd_acl_with_owner_restricted(acl):
    jd = JD(id="jd1", jd_title="X", owner_agent_id="hh-A")
    assert acl.can_view_jd("hh-A", jd)
    assert not acl.can_view_jd("hh-B", jd)
    assert acl.can_view_jd("admin1", jd)  # 平台


def test_match_acl_by_fee_split(acl):
    """Match 可见性: 在 fee_split 中或管理员"""
    m1 = Match(id="m1", jd_id="j1", candidate_id="c1")
    from zhongjie.domain.models import FeeShare
    m1.set_fee_split([FeeShare("hh-A", 0.6), FeeShare("hh-B", 0.4)])

    # hh-A 和 hh-B 在分润中 → 可见
    assert acl.can_view_match("hh-A", m1)
    assert acl.can_view_match("hh-B", m1)
    # hh-C 不在分润中 → 不可见
    assert not acl.can_view_match("hh-C", m1)
    # 平台管理员可见
    assert acl.can_view_match("admin1", m1)


def test_match_filter_visible(acl):
    from zhongjie.domain.models import FeeShare
    m1 = Match(id="m1")
    m1.set_fee_split([FeeShare("hh-A", 0.5), FeeShare("hh-B", 0.5)])
    m2 = Match(id="m2")
    m2.set_fee_split([FeeShare("hh-C", 1.0)])
    visible = acl.filter_visible_matches("hh-A", [m1, m2])
    assert len(visible) == 1
    assert visible[0].id == "m1"
