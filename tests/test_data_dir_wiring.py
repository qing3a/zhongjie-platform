"""
DATA_DIR env 路由测试
覆盖 bug: get_audit_log / build_domain_services / get_agent_registry 等单例
之前硬编码 data_dir="data", 忽略 DATA_DIR env, 导致 e2e demo 读不到写入数据。
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """隔离 DATA_DIR, 测试后还原"""
    custom_dir = tmp_path / "custom_data"
    custom_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(custom_dir))
    # 重要: deps 用了 lru_cache, 必须在设置 env 后再 import / reset
    from zhongjie.api import deps
    deps.reset_all()
    yield custom_dir
    deps.reset_all()
    monkeypatch.delenv("DATA_DIR", raising=False)


def test_get_data_dir_default(monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    from zhongjie.api import deps
    assert deps.get_data_dir() == "data"


def test_get_data_dir_reads_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "x"))
    from zhongjie.api import deps
    assert deps.get_data_dir() == str(tmp_path / "x")


def test_audit_log_uses_data_dir(clean_env):
    """get_audit_log 持久化文件应落在 DATA_DIR, 不是默认 'data/'"""
    from zhongjie.api import deps
    log = deps.get_audit_log()
    # 校验内部 path 位于 DATA_DIR
    assert str(clean_env) in str(log._path)
    assert log._path.name == "governance_audit.json"


def test_agent_registry_uses_data_dir(clean_env):
    from zhongjie.api import deps
    reg = deps.get_agent_registry()
    assert str(clean_env) in str(reg._path)
    assert reg._path.name == "agents.json"


def test_task_manager_uses_data_dir(clean_env):
    from zhongjie.api import deps
    tm = deps.get_task_manager()
    assert str(clean_env) in str(tm._path)
    assert tm._path.name == "tasks.json"


def test_delegation_manager_uses_data_dir(clean_env):
    from zhongjie.api import deps
    dm = deps.get_delegation_manager()
    assert str(clean_env) in str(dm._path)
    assert dm._path.name == "delegations.json"


def test_billing_service_uses_data_dir(clean_env):
    from zhongjie.api import deps
    bs = deps.get_billing_service()
    assert str(clean_env) in str(bs._path)
    assert bs._path.name == "invoices.json"


def test_data_dir_change_after_reset_takes_effect(monkeypatch, tmp_path):
    """DATA_DIR 改变 + reset_all() 后, 后续单例应使用新 DATA_DIR
    (这是 e2e demo 能复用的关键: 在新 DATA_DIR 下创建审计条目, HTTP 读也能读到)
    """
    from zhongjie.api import deps

    dir_a = tmp_path / "dir_a"; dir_a.mkdir()
    dir_b = tmp_path / "dir_b"; dir_b.mkdir()

    # 在 dir_a 下创建日志
    monkeypatch.setenv("DATA_DIR", str(dir_a))
    deps.reset_all()
    log_a = deps.get_audit_log()
    log_a.append(_fake_entry("req_a", "agent-1", "rule_match", 0.5))
    path_a = log_a._path
    assert path_a.exists()
    assert (dir_a / "governance_audit.json") == path_a

    # 切到 dir_b, 重建单例
    monkeypatch.setenv("DATA_DIR", str(dir_b))
    deps.reset_all()
    log_b = deps.get_audit_log()
    log_b.append(_fake_entry("req_b", "agent-2", "rule_match", 0.6))
    path_b = log_b._path
    assert (dir_b / "governance_audit.json") == path_b
    assert path_a != path_b  # 路径不同
    # dir_b 应该有 1 条, dir_a 应该有 1 条
    assert len(list(path_a.parent.glob("*.json"))) >= 1
    assert path_b.exists()
    # log_b 应只看到 dir_b 的内容
    assert log_b.count() == 1


def _fake_entry(req_id, agent_id, decision, trust):
    """构造一条审计条目"""
    from zhongjie.governance.audit import AuditEntry
    from datetime import UTC, datetime
    return AuditEntry(
        id=f"aud_{req_id}",
        request_id=req_id,
        owner_agent_id=agent_id,
        decision=decision,
        matched_rule=None,
        trust_score=trust,
        timestamp=datetime.now(UTC).isoformat(),
    )
