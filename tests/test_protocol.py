"""
M5 单元测试 - 验证协议分发器抽象 + 兼容老 Skill Link 行为
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.protocol.headhunter_skill import HeadhunterSkill
from zhongjie.protocol.legacy_skill_link import LegacySkillLinkDispatcher
from zhongjie.protocol.responses import skill_error, skill_pending, skill_success


def test_response_helpers_have_unified_shape():
    """统一响应: status/code/data/message/meta 五字段"""
    s = skill_success("OK", {"a": 1}, "done")
    assert s["status"] == "success"
    assert s["code"] == "OK"
    assert s["data"] == {"a": 1}
    assert "timestamp" in s["meta"]

    e = skill_error("ERR_X", "bad", http_status=400)
    assert e["status"] == "error"
    assert e["meta"]["http_status"] == 400

    p = skill_pending("PENDING", {"task_id": "t1"}, "wait")
    assert p["status"] == "pending"
    assert p["data"]["task_id"] == "t1"


def test_headhunter_skill_submit_jd(tmp_path):
    h = Headhunter_skill_factory(tmp_path)
    r = h.handle("submit_jd", {"jd_title": "P7 数据岗", "jd_level": "P7",
                                "salary_range": "50-80K", "requirements": ["Python"]},
                 context={"agent_id": "hh-A"})
    assert r["status"] == "success"
    assert r["code"] == "JD_SUBMITTED"
    assert r["data"]["jd_id"].startswith("jd_")
    assert r["data"]["owner_agent_id"] == "hh-A"  # P1 接入预留位


def test_headhunter_skill_submit_candidate_masks(tmp_path):
    h = Headhunter_skill_factory(tmp_path)
    r = h.handle("submit_candidate", {
        "candidate_name": "李四", "phone": "13912345678",
        "email": "lisi@test.com", "skills": ["Python"]
    }, context={"agent_id": "hh-B"})
    assert r["status"] == "success"
    assert r["code"] == "CANDIDATE_SUBMITTED"
    # 验证 data 里不带明文（mask 在 repository 内部）
    candidate_id = r["data"]["candidate_id"]
    stored = h.candidate.get(candidate_id)
    assert stored.candidate_name == "李*"
    assert stored.phone == "139****5678"
    assert stored.email == "l***@test.com"


def test_headhunter_skill_submit_match_with_invalid_refs(tmp_path):
    h = Headhunter_skill_factory(tmp_path)
    # 缺参
    r = h.handle("submit_match", {})
    assert r["status"] == "error"
    assert r["code"] == "ERR_MISSING_PARAM"

    # 不存在的 jd
    r = h.handle("submit_match", {"jd_id": "jd_fake", "candidate_id": "cand_fake"})
    assert r["status"] == "error"
    assert r["code"] == "ERR_NOT_FOUND"


def test_headhunter_skill_submit_match_pending(tmp_path):
    """合法 match: 返回 pending 状态（与老 api_server.py:1413 一致）"""
    h = Headhunter_skill_factory(tmp_path)
    jd_r = h.handle("submit_jd", {"jd_title": "X"})
    cand_r = h.handle("submit_candidate", {"candidate_name": "A"})
    r = h.handle("submit_match", {
        "jd_id": jd_r["data"]["jd_id"],
        "candidate_id": cand_r["data"]["candidate_id"],
    })
    assert r["status"] == "pending"
    assert r["code"] == "REQUEST_PENDING"
    assert r["data"]["match_id"].startswith("match_")


def test_legacy_skill_link_dispatcher_routes_correctly(tmp_path):
    """Dispatcher: skill_name+action 正确路由"""
    d = LegacySkillLinkDispatcher(data_dir=str(tmp_path))
    r = d.dispatch({
        "skill_name": "猎头_skill",
        "action": "submit_jd",
        "data": {"jd_title": "测试 JD"},
    }, context={"agent_id": "hh-A"})
    assert r["status"] == "success"
    assert r["data"]["jd_id"].startswith("jd_")


def test_legacy_dispatcher_unknown_skill(tmp_path):
    d = LegacySkillLinkDispatcher(data_dir=str(tmp_path))
    r = d.dispatch({"skill_name": "unknown_skill", "action": "x"})
    assert r["status"] == "error"
    assert r["code"] == "ERR_NOT_FOUND"


def test_legacy_dispatcher_unknown_action(tmp_path):
    d = LegacySkillLinkDispatcher(data_dir=str(tmp_path))
    r = d.dispatch({"skill_name": "猎头_skill", "action": "unknown_action"})
    assert r["status"] == "error"


def test_legacy_dispatcher_missing_params(tmp_path):
    d = LegacySkillLinkDispatcher(data_dir=str(tmp_path))
    r = d.dispatch({})
    assert r["status"] == "error"
    assert r["code"] == "ERR_MISSING_PARAM"


def test_legacy_dispatcher_list_skills():
    """list_skills 返回所有 skills（可用于 A2A Agent Card）"""
    d = LegacySkillLinkDispatcher(data_dir="data")
    skills = d.list_skills()
    assert len(skills) == 1
    assert skills[0]["skill_name"] == "猎头_skill"
    assert "submit_jd" in skills[0]["actions"]


# 工具
def Headhunter_skill_factory(tmp_path: Path) -> HeadhunterSkill:
    """为测试创建 HeadhunterSkill 实例，使用隔离的临时数据目录"""
    from zhongjie.domain.factory import build_services
    jd, cand, match = build_services(str(tmp_path))
    return HeadhunterSkill(jd, cand, match)
