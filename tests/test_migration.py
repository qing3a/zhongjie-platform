"""
M9 单元测试 - 数据迁移 + 身份桥接
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from zhongjie.identity.agent_card import AgentRole, AgentTier
from zhongjie.identity.bridge import IdentityBridge
from zhongjie.identity.registry import AgentRegistry

# 跑迁移脚本需要 utf-8 (脚本含 emoji, Windows GBK 默认会崩)
SCRIPTS_DIR = ROOT / "scripts"
_SUBPROCESS_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def test_bridge_ensure_agent_creates_new(tmp_path):
    """新 key: 自动建 Agent"""
    reg = AgentRegistry(data_dir=tmp_path)
    bridge = IdentityBridge(reg)
    agent_id = bridge.ensure_agent_for_token(
        key_id="ak_abc", key_name="猎头A公司", role="requester"
    )
    assert agent_id.startswith("agent_")
    # 验证注册表
    card = reg.get(agent_id)
    assert card is not None
    assert card.name == "猎头A公司"
    assert card.role == AgentRole.HEADHUNTER
    assert "candidate_sourcing" in card.capabilities


def test_bridge_ensure_agent_returns_existing(tmp_path):
    """老 key 第二次: 返回同一个 agent_id"""
    reg = AgentRegistry(data_dir=tmp_path)
    bridge = IdentityBridge(reg)
    id1 = bridge.ensure_agent_for_token("ak_a", "猎头A", "requester")
    id2 = bridge.ensure_agent_for_token("ak_b", "猎头A", "requester")
    assert id1 == id2


def test_bridge_role_mapping():
    """role 字符串 → AgentRole 映射"""
    from zhongjie.identity.bridge import ROLE_TO_AGENT_ROLE
    assert ROLE_TO_AGENT_ROLE["requester"] == AgentRole.HEADHUNTER
    assert ROLE_TO_AGENT_ROLE["admin"] == AgentRole.PLATFORM


def test_migration_adds_owner_field_to_existing_data(tmp_path):
    """迁移：老数据无 owner_agent_id → 加 'legacy'"""
    # 准备老数据
    jd = [{"id": "jd_1", "jd_title": "X"}, {"id": "jd_2", "jd_title": "Y"}]
    (tmp_path / "jd.json").write_text(json.dumps(jd, ensure_ascii=False), encoding="utf-8")
    cand = [{"id": "cand_1", "candidate_name": "A"}]
    (tmp_path / "candidates.json").write_text(json.dumps(cand, ensure_ascii=False), encoding="utf-8")

    # 跑迁移脚本
    result = subprocess.run(
        ["python", str(SCRIPTS_DIR / "migrate_add_owner.py"),
         "--data-dir", str(tmp_path), "--no-backup"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=_SUBPROCESS_ENV,
    )
    assert result.returncode == 0, f"迁移失败: {result.stderr}"

    # 验证 jd.json
    jd_after = json.loads((tmp_path / "jd.json").read_text(encoding="utf-8"))
    assert all(item.get("owner_agent_id") == "legacy" for item in jd_after)
    assert len(jd_after) == 2
    # 原字段保留
    assert jd_after[0]["jd_title"] == "X"

    # 验证 candidates.json
    cand_after = json.loads((tmp_path / "candidates.json").read_text(encoding="utf-8"))
    assert cand_after[0]["owner_agent_id"] == "legacy"


def test_migration_skips_records_already_with_owner(tmp_path):
    """迁移：已有 owner_agent_id 的记录不改"""
    data = [
        {"id": "jd_1", "owner_agent_id": "agent_existing"},
        {"id": "jd_2"},  # 没 owner
    ]
    (tmp_path / "jd.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        ["python", str(SCRIPTS_DIR / "migrate_add_owner.py"),
         "--data-dir", str(tmp_path), "--no-backup"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=_SUBPROCESS_ENV,
    )
    assert result.returncode == 0
    after = json.loads((tmp_path / "jd.json").read_text(encoding="utf-8"))
    assert after[0]["owner_agent_id"] == "agent_existing"  # 不变
    assert after[1]["owner_agent_id"] == "legacy"


def test_migration_dry_run_does_not_modify(tmp_path):
    """dry-run 模式: 不真改文件"""
    data = [{"id": "jd_1"}]
    (tmp_path / "jd.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        ["python", str(SCRIPTS_DIR / "migrate_add_owner.py"),
         "--data-dir", str(tmp_path), "--dry-run", "--no-backup"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=_SUBPROCESS_ENV,
    )
    assert result.returncode == 0
    # 文件未变
    after = json.loads((tmp_path / "jd.json").read_text(encoding="utf-8"))
    assert "owner_agent_id" not in after[0]


def test_migration_handles_missing_files(tmp_path):
    """文件不存在时: 优雅跳过"""
    result = subprocess.run(
        ["python", str(SCRIPTS_DIR / "migrate_add_owner.py"),
         "--data-dir", str(tmp_path), "--no-backup"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=_SUBPROCESS_ENV,
    )
    assert result.returncode == 0
    assert "不存在" in result.stdout or "missing" in result.stdout.lower()


def test_migrated_data_loads_into_new_repo(tmp_path):
    """迁移后的数据能被新 Repository 正确加载（含 owner_agent_id）"""
    # 模拟老数据 + 迁移
    data = [
        {"id": "jd_1", "jd_title": "X"},
        {"id": "jd_2", "jd_title": "Y"},
    ]
    (tmp_path / "jd.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    subprocess.run(
        ["python", str(SCRIPTS_DIR / "migrate_add_owner.py"),
         "--data-dir", str(tmp_path), "--no-backup"],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", env=_SUBPROCESS_ENV,
    )
    # 新 Repository 加载
    from zhongjie.domain.factory import build_services
    jd_svc, _, _ = build_services(str(tmp_path))
    jd1 = jd_svc.get("jd_1")
    assert jd1 is not None
    assert jd1.owner_agent_id == "legacy"
