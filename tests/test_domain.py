"""
M2 单元测试 - 验证领域层独立可用 + 老数据格式兼容
"""
import json
import sys
import tempfile
from pathlib import Path

# 把 src/ 加入路径，让 zhongjie 包可导入
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.domain.factory import build_services
from zhongjie.domain.masking import (
    mask_email, mask_phone, mask_sensitive_data, mask_salary
)
from zhongjie.domain.models import Candidate, JD, Match
from zhongjie.domain.repositories import InMemoryRepository


def test_masking_basics():
    """脱敏工具: 行为与老 api_server.py 一致"""
    assert mask_phone("13800138000") == "138****8000"
    assert mask_email("alice@example.com") == "a***@example.com"
    assert mask_salary("30-50K", "partial") == "30-50K"
    # 名字保留首字
    out = mask_sensitive_data({"candidate_name": "张三"})
    assert out["candidate_name"] == "张*"


def test_models_from_dict_legacy():
    """老 JSON 数据（无 owner_agent_id 字段）能正常解析"""
    legacy_jd = {
        "id": "jd_abc", "jd_title": "Python 工程师", "jd_level": "P6",
        "salary_range": "30-50K", "requirements": ["Python", "FastAPI"],
        "status": "active", "created_at": "2026-01-01T00:00:00",
    }
    jd = JD.from_dict(legacy_jd)
    assert jd.id == "jd_abc"
    assert jd.owner_agent_id is None  # 老数据无此字段，自动 None
    assert jd.jd_title == "Python 工程师"


def test_repository_thread_safe_save_and_persist(tmp_dir: Path):
    """Repository 线程安全 + 持久化原子写"""
    repo = InMemoryRepository[JD](
        data_dir=tmp_dir, filename="jd.json", from_dict=JD.from_dict
    )
    jd = JD(id="jd_1", jd_title="Test", owner_agent_id="hh-A")
    repo.save(jd)
    repo.persist()
    assert (tmp_dir / "jd.json").exists()
    # 验证原子写：不应有遗留 .tmp
    assert not (tmp_dir / "jd.tmp").exists()
    # 重新读取
    repo2 = InMemoryRepository[JD](
        data_dir=tmp_dir, filename="jd.json", from_dict=JD.from_dict
    )
    count = repo2.load()
    assert count == 1
    loaded = repo2.get("jd_1")
    assert loaded is not None
    assert loaded.jd_title == "Test"
    assert loaded.owner_agent_id == "hh-A"


def test_service_submit_jd(tmp_dir: Path):
    """JDService.submit: 创建+持久化+可查询"""
    jd_svc, _, _ = build_services(str(tmp_dir))
    jd = jd_svc.submit({
        "jd_title": "高级 Python",
        "jd_level": "P7",
        "salary_range": "50-80K",
        "requirements": ["Python", "LLM"],
    }, owner_agent_id="hh-A")
    assert jd.id.startswith("jd_")
    assert jd.owner_agent_id == "hh-A"
    assert (tmp_dir / "jd.json").exists()
    # 重新 build 能查回
    jd_svc2, _, _ = build_services(str(tmp_dir))
    fetched = jd_svc2.get(jd.id)
    assert fetched is not None
    assert fetched.jd_title == "高级 Python"


def test_service_submit_candidate_masks_sensitive(tmp_dir: Path):
    """CandidateService.submit: 自动脱敏"""
    _, cand_svc, _ = build_services(str(tmp_dir))
    cand = cand_svc.submit({
        "candidate_name": "李四",
        "phone": "13912345678",
        "email": "lisi@test.com",
        "expected_salary": "30-50K",
        "skills": ["Python"],
    })
    assert cand.candidate_name == "李*"
    assert cand.phone == "139****5678"
    assert cand.email == "l***@test.com"


def test_service_submit_match_validates_refs(tmp_dir: Path):
    """MatchService.submit: 校验 jd/candidate 存在"""
    jd_svc, cand_svc, match_svc = build_services(str(tmp_dir))
    jd = jd_svc.submit({"jd_title": "Test"})
    cand = cand_svc.submit({"candidate_name": "张三"})

    # 正常
    m, err = match_svc.submit({"jd_id": jd.id, "candidate_id": cand.id})
    assert err is None
    assert m.status == "pending"

    # 不存在的 jd
    m, err = match_svc.submit({"jd_id": "jd_fake", "candidate_id": cand.id})
    assert m is None and err == "ERR_NOT_FOUND_JD"

    # 缺参
    m, err = match_svc.submit({})
    assert m is None and err == "ERR_MISSING_PARAM"


# 测试辅助
import pytest

@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """隔离的临时数据目录"""
    d = tmp_path / "data"
    d.mkdir()
    return d


def test_legacy_json_loads_into_new_repo(tmp_dir: Path):
    """把老格式 jd.json 放进新 Repository，能正常 load"""
    legacy = [
        {
            "id": "jd_legacy1", "jd_title": "Legacy JD", "jd_level": "P5",
            "salary_range": "20-30K", "requirements": ["Go"],
            "status": "active", "created_at": "2026-01-01T00:00:00"
        }
    ]
    (tmp_dir / "jd.json").write_text(
        json.dumps(legacy, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    jd_svc, _, _ = build_services(str(tmp_dir))
    assert jd_svc.get("jd_legacy1") is not None
    assert jd_svc.get("jd_legacy1").jd_title == "Legacy JD"
