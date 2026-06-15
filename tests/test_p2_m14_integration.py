"""
P2 M14 集成测试 - 端到端场景: 分享+分润+ACL+持久化
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import zhongjie.domain.factory as factory_mod
from zhongjie.domain.models import Candidate, FeeShare, Match
from zhongjie.governance.acl import AccessControl


def test_end_to_end_share_and_split_scenario(tmp_path):
    """场景: 猎头 A 拥有候选人 → 分享给 B → 创建 match (A+B+平台分润) → 验证 ACL"""

    # === 阶段 1: A 创建 JD 和 Candidate ===
    jd_svc, cand_svc, match_svc = factory_mod.build_services(str(tmp_path))
    jd = jd_svc.submit({
        "jd_title": "高级金融工程师",
        "jd_level": "P7",
        "salary_range": "50-80K",
        "requirements": ["Python", "金融"],
    }, owner_agent_id="hh-A")
    cand = cand_svc.submit({
        "candidate_name": "李四",
        "phone": "13912345678",
        "email": "lisi@test.com",
        "skills": ["Python", "Finance"],
    }, owner_agent_id="hh-A")

    assert cand.owner_agent_id == "hh-A"
    assert cand.visibility == "private"

    # === 阶段 2: ACL 验证: B/C 看不到 (private) ===
    acl = AccessControl(agent_roles={
        "hh-A": "headhunter", "hh-B": "headhunter",
        "hh-C": "headhunter", "admin1": "admin",
    })
    assert acl.can_view_candidate("hh-A", cand)
    assert not acl.can_view_candidate("hh-B", cand)
    assert not acl.can_view_candidate("hh-C", cand)
    # 平台管理员
    assert acl.can_view_candidate("admin1", cand)

    # === 阶段 3: A 分享给 B ===
    success, err = cand_svc.share_to("hh-A", cand.id, "hh-B", ref_id="deleg_001")
    assert success
    assert err is None
    cand_after = cand_svc.get(cand.id)
    assert cand_after.visibility == "shared"
    assert "hh-B" in cand_after.shared_with
    # ACL 更新
    assert acl.can_view_candidate("hh-B", cand_after)
    assert not acl.can_view_candidate("hh-C", cand_after)
    # provenance 记录
    actions = [p["action"] for p in cand_after.provenance]
    assert "created" in actions
    assert "shared" in actions

    # === 阶段 4: 创建 match (三方分润) ===
    match, err = match_svc.submit({"jd_id": jd.id, "candidate_id": cand.id})
    assert match is not None
    match.set_fee_split([
        FeeShare("hh-A", 0.4, role="co_finder"),
        FeeShare("hh-B", 0.5, role="co_finder"),
        FeeShare("platform", 0.1, role="platform_fee"),
    ])
    match_svc._repo.save(match)  # 持久化

    # === 阶段 5: 验证 match ACL（按 fee_split）===
    assert acl.can_view_match("hh-A", match)
    assert acl.can_view_match("hh-B", match)
    assert not acl.can_view_match("hh-C", match)  # 不在分润中
    assert acl.can_view_match("admin1", match)

    # === 阶段 6: 验证 FeeShare 业务 ===
    assert match.total_pct() == pytest.approx(1.0)
    assert match.is_valid_fee_split()
    assert match.fee_share_for("hh-A").pct == 0.4
    assert match.fee_share_for("platform").role == "platform_fee"

    # === 阶段 7: 取消分享（应自动回退到 private）===
    cand_svc.unshare("hh-A", cand.id, "hh-B")
    cand_after2 = cand_svc.get(cand.id)
    assert cand_after2.visibility == "private"
    assert "hh-B" not in cand_after2.shared_with

    # === 阶段 8: 持久化 + 重载验证 ===
    jd2, cand2, match2 = factory_mod.build_services(str(tmp_path))
    cand_reloaded = cand2.get(cand.id)
    assert cand_reloaded is not None
    assert cand_reloaded.owner_agent_id == "hh-A"
    # provenance 也持久化
    assert len(cand_reloaded.provenance) >= 2

    # match 也持久化
    match_reloaded = match2.get(match.id)
    assert match_reloaded is not None
    assert match_reloaded.fee_share_for("hh-A").pct == 0.4


def test_owner_cannot_share_others_candidate(tmp_path):
    """核心安全测试: 猎头 B 不能分享猎头 A 的候选人"""
    _, cand_svc, _ = factory_mod.build_services(str(tmp_path))
    cand = cand_svc.submit({"candidate_name": "X"}, owner_agent_id="hh-A")

    # hh-B 试图分享给 hh-C
    success, err = cand_svc.share_to("hh-B", cand.id, "hh-C")
    assert not success
    assert err == "ERR_NOT_OWNER"

    # 状态未变
    cand_after = cand_svc.get(cand.id)
    assert "hh-C" not in cand_after.shared_with
    assert cand_after.visibility == "private"


def test_three_way_split_validation(tmp_path):
    """三方分润验证失败场景"""
    _, _, match_svc = factory_mod.build_services(str(tmp_path))

    # 合法
    m1 = Match(id="m1")
    m1.set_fee_split([
        FeeShare("hh-A", 0.4), FeeShare("hh-B", 0.5), FeeShare("platform", 0.1)
    ])
    assert m1.is_valid_fee_split()

    # 平台抽佣过多
    from zhongjie.domain.models import FeeShareValidationError
    m2 = Match(id="m2")
    with pytest.raises(FeeShareValidationError):
        m2.set_fee_split([
            FeeShare("hh-A", 0.3), FeeShare("hh-B", 0.3), FeeShare("platform", 0.3)
        ])  # 0.9 ≠ 1.0

    # 平台抽佣 0%
    m3 = Match(id="m3")
    m3.set_fee_split([FeeShare("hh-A", 0.5), FeeShare("hh-B", 0.5)])
    assert m3.is_valid_fee_split()


def test_acl_filter_visible_in_real_world(tmp_path):
    """真实场景: 多个候选人，ACL 过滤"""
    _, cand_svc, _ = factory_mod.build_services(str(tmp_path))

    # A 录 3 个候选人
    c1 = cand_svc.submit({"candidate_name": "A1"}, owner_agent_id="hh-A")
    c2 = cand_svc.submit({"candidate_name": "A2"}, owner_agent_id="hh-A")
    c3 = cand_svc.submit({"candidate_name": "A3"}, owner_agent_id="hh-A")
    # A 分享 c2 给 B
    cand_svc.share_to("hh-A", c2.id, "hh-B")
    # B 自己录 1 个
    c4 = cand_svc.submit({"candidate_name": "B1"}, owner_agent_id="hh-B")

    all_cands = [c1, c2, c3, c4]

    acl = AccessControl(agent_roles={"hh-A": "headhunter", "hh-B": "headhunter"})

    # A 可见: c1, c2, c3 (自己) + c4 (看不到, 别人 private)
    visible_to_A = acl.filter_visible_candidates("hh-A", all_cands)
    assert {c.id for c in visible_to_A} == {c1.id, c2.id, c3.id}

    # B 可见: c2 (A 分享的) + c4 (自己的)
    visible_to_B = acl.filter_visible_candidates("hh-B", all_cands)
    assert {c.id for c in visible_to_B} == {c2.id, c4.id}
