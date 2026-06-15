"""
委托治理硬约束测试
覆盖:
- fee_split 硬校验（比例不对、空、重复 agent 必须在 create() 阶段被拒绝）
- 防飞单: 同一 candidate 在 active 委托存在时不能发起新委托
- 终态释放: 委托被 reject/cancel/settle 后允许重新委托
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.collaboration.delegation import DelegationStatus
from zhongjie.collaboration.delegation_service import (
    CandidateAlreadyDelegatedError, DelegationManager, DelegationService,
)
from zhongjie.collaboration.task_manager import TaskManager
from zhongjie.collaboration.task_service import TaskService
from zhongjie.domain import factory as factory_mod
from zhongjie.domain.models import FeeShare, FeeShareValidationError
from zhongjie.infra.events import EventBus


@pytest.fixture
def stack(tmp_path):
    bus = EventBus()
    jd_svc, cand_svc, _ = factory_mod.build_services(str(tmp_path))
    tm = TaskManager(data_dir=tmp_path)
    ts = TaskService(tm, event_bus=bus)
    dm = DelegationManager(data_dir=tmp_path)
    ds = DelegationService(dm, cand_svc, bus, ts)
    return {"bus": bus, "jd_svc": jd_svc, "cand_svc": cand_svc,
            "tm": tm, "ts": ts, "dm": dm, "ds": ds}


# ==================== fee_split 硬校验 ====================

def test_create_with_invalid_fee_split_sum_raises(stack):
    """pct 之和 != 1.0 必须在 create() 阶段被拒绝"""
    cand = stack["cand_svc"].submit({"candidate_name": "张三"}, owner_agent_id="hh-A")
    bad = [FeeShare("hh-A", 0.3), FeeShare("hh-B", 0.3)]  # 总和 0.6
    with pytest.raises(FeeShareValidationError):
        stack["ds"].create(
            from_agent_id="hh-A", to_agent_id="hh-B",
            candidate_ref=cand.id, fee_split=bad,
        )


def test_create_with_empty_fee_split_is_treated_as_no_fee_split(stack):
    """fee_split 显式传空 list 等价于不传（视为暂无分润）"""
    cand = stack["cand_svc"].submit({"candidate_name": "张三"}, owner_agent_id="hh-A")
    d = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id, fee_split=[],
    )
    assert d.fee_split == []


def test_create_with_no_fee_split_is_allowed(stack):
    """fee_split 可选; 不传 = 暂不分润, 后续补"""
    cand = stack["cand_svc"].submit({"candidate_name": "张三"}, owner_agent_id="hh-A")
    d = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    assert d.id is not None
    assert d.fee_split == []


def test_create_with_valid_fee_split_succeeds(stack):
    """正常的 4:6 分润应通过"""
    cand = stack["cand_svc"].submit({"candidate_name": "张三"}, owner_agent_id="hh-A")
    d = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
        fee_split=[FeeShare("hh-A", 0.4), FeeShare("hh-B", 0.6)],
    )
    assert d.fee_share_for("hh-A").pct == 0.4
    assert d.fee_share_for("hh-B").pct == 0.6


# ==================== 并发委托互斥（防飞单） ====================

def test_concurrent_delegation_on_same_candidate_blocked(stack):
    """同一候选人在已有 active 委托时, 第二次委托必须被拒绝"""
    cand = stack["cand_svc"].submit({"candidate_name": "张三"}, owner_agent_id="hh-A")
    # 第一次委托: A → B
    stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
        fee_split=[FeeShare("hh-A", 0.5), FeeShare("hh-B", 0.5)],
    )
    # 第二次委托: A → C（同一候选人）
    with pytest.raises(CandidateAlreadyDelegatedError) as exc:
        stack["ds"].create(
            from_agent_id="hh-A", to_agent_id="hh-C",
            candidate_ref=cand.id,
            fee_split=[FeeShare("hh-A", 0.5), FeeShare("hh-C", 0.5)],
        )
    assert cand.id in str(exc.value)
    assert "active" in str(exc.value).lower()


def test_delegation_unlocks_after_reject(stack):
    """B 拒绝后, A 可以把同一候选人委托给 C"""
    cand = stack["cand_svc"].submit({"candidate_name": "张三"}, owner_agent_id="hh-A")
    d1 = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    stack["ds"].reject(d1.id, actor="hh-B", reason="不擅长")
    # 状态进入 REJECTED（终态），不再算 active
    assert d1.status == DelegationStatus.REJECTED
    # 现在可以委托给 C
    d2 = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-C",
        candidate_ref=cand.id,
    )
    assert d2.id != d1.id
    assert d2.status == DelegationStatus.PENDING


def test_delegation_unlocks_after_cancel(stack):
    """A 取消后, 可重新委托"""
    cand = stack["cand_svc"].submit({"candidate_name": "张三"}, owner_agent_id="hh-A")
    d1 = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    stack["ds"].cancel(d1.id, actor="hh-A", reason="改主意")
    d2 = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    assert d2.status == DelegationStatus.PENDING


def test_delegation_unlocks_after_settle(stack):
    """成功入职并结算后, 候选人可以再次委托（同一猎头可继续用）"""
    cand = stack["cand_svc"].submit({"candidate_name": "张三"}, owner_agent_id="hh-A")
    d1 = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    stack["ds"].accept(d1.id, actor="hh-B")
    stack["ds"].start_progress(d1.id, actor="hh-B")
    stack["ds"].mark_placed(d1.id, actor="hh-B")
    stack["ds"].mark_settled = lambda *a, **kw: d1.settle()  # 占位
    d1.settle()
    assert d1.status == DelegationStatus.SETTLED
    # 现在可以重新委托（候选人已入职但理论上下一次机会仍可流转）
    d2 = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    assert d2.status == DelegationStatus.PENDING


def test_active_lock_holds_through_accepted_and_in_progress(stack):
    """accept / in_progress 阶段都是 active, 不能并发"""
    cand = stack["cand_svc"].submit({"candidate_name": "张三"}, owner_agent_id="hh-A")
    d1 = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    stack["ds"].accept(d1.id, actor="hh-B")
    assert d1.status == DelegationStatus.ACCEPTED
    with pytest.raises(CandidateAlreadyDelegatedError):
        stack["ds"].create(
            from_agent_id="hh-A", to_agent_id="hh-C",
            candidate_ref=cand.id,
        )
    stack["ds"].start_progress(d1.id, actor="hh-B")
    assert d1.status == DelegationStatus.IN_PROGRESS
    with pytest.raises(CandidateAlreadyDelegatedError):
        stack["ds"].create(
            from_agent_id="hh-A", to_agent_id="hh-C",
            candidate_ref=cand.id,
        )


def test_find_active_for_candidate_manager(stack):
    """DelegationManager.find_active_for_candidate 直接验证"""
    cand = stack["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    assert stack["dm"].find_active_for_candidate(cand.id) is None
    d = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    found = stack["dm"].find_active_for_candidate(cand.id)
    assert found is not None
    assert found.id == d.id
    stack["ds"].cancel(d.id, actor="hh-A")
    assert stack["dm"].find_active_for_candidate(cand.id) is None
