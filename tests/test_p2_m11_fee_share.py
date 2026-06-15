"""
P2 M11 测试 - FeeShare 模型 + Match.fee_split 验证
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.domain.models import (
    FeeShare, FeeShareValidationError, Match, validate_fee_split
)


def test_fee_share_basic():
    s = FeeShare(agent_id="hh-A", pct=0.4)
    assert s.pct == 0.4
    assert s.role == "co_finder"
    assert s.settled is False


def test_fee_share_pct_bounds():
    import pytest
    with pytest.raises(ValueError):
        FeeShare(agent_id="x", pct=1.5)
    with pytest.raises(ValueError):
        FeeShare(agent_id="x", pct=-0.1)


def test_fee_share_round_trip():
    s = FeeShare(agent_id="hh-A", pct=0.4, role="owner")
    d = s.to_dict()
    s2 = FeeShare.from_dict(d)
    assert s2.agent_id == s.agent_id
    assert s2.pct == s.pct
    assert s2.role == s.role


def test_validate_fee_split_valid():
    """两个 share: 0.4 + 0.6 = 1.0"""
    shares = [FeeShare("hh-A", 0.4), FeeShare("hh-B", 0.6)]
    validate_fee_split(shares)  # 不抛


def test_validate_fee_split_with_tolerance():
    """浮点误差容忍"""
    shares = [FeeShare("hh-A", 0.4), FeeShare("hh-B", 0.4), FeeShare("hh-C", 0.2)]
    validate_fee_split(shares)


def test_validate_fee_split_sum_invalid():
    """pct 之和 != 1.0 → 报错"""
    shares = [FeeShare("hh-A", 0.4), FeeShare("hh-B", 0.5)]
    with pytest.raises(FeeShareValidationError, match="pct 之和"):
        validate_fee_split(shares)


def test_validate_fee_split_duplicate_agent():
    """agent_id 重复 → 报错"""
    shares = [FeeShare("hh-A", 0.4), FeeShare("hh-A", 0.6)]
    with pytest.raises(FeeShareValidationError, match="agent_id 重复"):
        validate_fee_split(shares)


def test_validate_fee_split_empty():
    with pytest.raises(FeeShareValidationError, match="不能为空"):
        validate_fee_split([])


def test_validate_fee_split_accepts_dicts():
    """兼容从 JSON 读出的 dict list"""
    raw = [{"agent_id": "hh-A", "pct": 0.5}, {"agent_id": "hh-B", "pct": 0.5}]
    validate_fee_split(raw)  # 不抛


def test_match_set_fee_split():
    m = Match(id="m1")
    m.set_fee_split([FeeShare("hh-A", 0.4), FeeShare("hh-B", 0.6)])
    assert m.fee_split  # 非空
    assert m.total_pct() == pytest.approx(1.0)
    assert m.is_valid_fee_split()


def test_match_set_fee_split_invalid_raises():
    m = Match(id="m1")
    with pytest.raises(FeeShareValidationError):
        m.set_fee_split([FeeShare("hh-A", 0.3)])  # 不到 1.0
    # fee_split 未被破坏
    assert m.fee_split == []


def test_match_fee_share_for():
    m = Match(id="m1")
    m.set_fee_split([FeeShare("hh-A", 0.4), FeeShare("hh-B", 0.6)])
    assert m.fee_share_for("hh-A").pct == 0.4
    assert m.fee_share_for("hh-B").pct == 0.6
    assert m.fee_share_for("hh-C") is None


def test_match_legacy_data_loads():
    """老 match 记录 (无 fee_split 字段) 默认为空"""
    legacy = {"id": "m1", "jd_id": "jd_1", "candidate_id": "c_1"}
    m = Match.from_dict(legacy)
    assert m.fee_split == []
    assert m.is_valid_fee_split() is False  # 空不算合法


def test_match_with_three_way_split():
    """三方分润: 平台抽佣 + 两个猎头"""
    m = Match(id="m1")
    m.set_fee_split([
        FeeShare("hh-A", 0.35, role="co_finder"),
        FeeShare("hh-B", 0.55, role="co_finder"),
        FeeShare("platform", 0.10, role="platform_fee"),
    ])
    assert m.total_pct() == pytest.approx(1.0)
    assert m.fee_share_for("platform").pct == 0.10
    assert m.fee_share_for("platform").role == "platform_fee"
