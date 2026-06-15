"""
P4 M20 测试 - DelegationService
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import zhongjie.domain.factory as factory_mod
from zhongjie.collaboration.delegation import DelegationStatus
from zhongjie.collaboration.delegation_service import (
    DelegationManager, DelegationNotFoundError, DelegationService, PermissionError_
)
from zhongjie.collaboration.task_manager import TaskManager
from zhongjie.collaboration.task_service import TaskService
from zhongjie.domain.models import FeeShare
from zhongjie.infra.events import EventBus


@pytest.fixture
def stack(tmp_path):
    """完整依赖栈: factory + bus + task + delegation"""
    bus = EventBus()
    jd_svc, cand_svc, match_svc = factory_mod.build_services(str(tmp_path))
    tm = TaskManager(data_dir=tmp_path)
    ts = TaskService(tm, event_bus=bus)
    dm = DelegationManager(data_dir=tmp_path)
    ds = DelegationService(
        delegation_manager=dm, candidate_service=cand_svc,
        event_bus=bus, task_service=ts,
    )
    return {
        "bus": bus, "jd_svc": jd_svc, "cand_svc": cand_svc,
        "match_svc": match_svc, "tm": tm, "ts": ts, "dm": dm, "ds": ds,
    }


def test_create_delegation_with_acl_check(stack):
    """创建委托: 校验发起方是 owner"""
    cand = stack["cand_svc"].submit({"candidate_name": "张三"}, owner_agent_id="hh-A")
    d = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id, jd_context="P7 数据岗",
        fee_split=[FeeShare("hh-A", 0.4), FeeShare("hh-B", 0.6)],
    )
    assert d.status == DelegationStatus.PENDING
    assert d.from_agent_id == "hh-A"
    assert d.fee_share_for("hh-A").pct == 0.4
    # 关联 Task 已创建
    assert d.task_id is not None
    task = stack["ts"].get(d.task_id)
    assert task is not None


def test_create_acl_violation_raises(stack):
    """非 owner 不能发起委托"""
    cand = stack["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    with pytest.raises(PermissionError_):
        stack["ds"].create(
            from_agent_id="hh-C", to_agent_id="hh-B",
            candidate_ref=cand.id,
        )


def test_create_emits_event(stack):
    bus = stack["bus"]
    received = []
    bus.subscribe("delegation.created", lambda e: received.append(e))
    cand = stack["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    stack["ds"].create(from_agent_id="hh-A", to_agent_id="hh-B", candidate_ref=cand.id)
    assert len(received) == 1
    assert received[0].payload["from_agent_id"] == "hh-A"


def test_accept_shares_candidate(stack):
    """受托方接受委托: 自动把候选人加入 shared_with"""
    cand = stack["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    d = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id, visibility="masked",
    )
    # 接受前: B 看不到
    assert not cand.can_be_viewed_by("hh-B")
    # 接受
    stack["ds"].accept(d.id, actor="hh-B", note="我接")
    # 接受后: B 在 shared_with 中
    cand_after = stack["cand_svc"].get(cand.id)
    assert "hh-B" in cand_after.shared_with
    assert cand_after.can_be_viewed_by("hh-B")
    # 委托状态
    assert d.status == DelegationStatus.ACCEPTED


def test_accept_wrong_actor_fails(stack):
    cand = stack["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    d = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    # hh-C 不是受托方
    with pytest.raises(PermissionError_):
        stack["ds"].accept(d.id, actor="hh-C")


def test_reject_flow(stack):
    cand = stack["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    d = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    stack["ds"].reject(d.id, actor="hh-B", reason="不擅长")
    assert d.status == DelegationStatus.REJECTED
    # 候选人不会被分享
    cand_after = stack["cand_svc"].get(cand.id)
    assert "hh-B" not in cand_after.shared_with


def test_cancel_by_either_party(stack):
    cand = stack["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    d = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    # 接受后取消
    stack["ds"].accept(d.id, actor="hh-B")
    stack["ds"].cancel(d.id, actor="hh-A", reason="改主意了")
    assert d.status == DelegationStatus.CANCELLED


def test_list_for_agent(stack):
    cand = stack["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    cand2 = stack["cand_svc"].submit({"candidate_name": "Y"}, owner_agent_id="hh-A")
    stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-C",
        candidate_ref=cand2.id,
    )
    # hh-A 看到的: 2 个 (作为发起方)
    a_list = stack["ds"].list_for_agent("hh-A", role="from")
    assert len(a_list) == 2
    # hh-B 看到的: 1 个 (作为受托方)
    b_list = stack["ds"].list_for_agent("hh-B", role="to")
    assert len(b_list) == 1
    # hh-C 看到的: 1 个
    c_list = stack["ds"].list_for_agent("hh-C", role="to")
    assert len(c_list) == 1


def test_list_pending_for(stack):
    cand = stack["cand_svc"].submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    d1 = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    cand2 = stack["cand_svc"].submit({"candidate_name": "Y"}, owner_agent_id="hh-A")
    d2 = stack["ds"].create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand2.id,
    )
    # B 接受 d1
    stack["ds"].accept(d1.id, actor="hh-B")
    # B 看到的 pending: 只有 d2
    pending = stack["ds"].list_pending_for("hh-B")
    assert len(pending) == 1
    assert pending[0].id == d2.id


def test_persistence(tmp_path):
    """持久化: 一个 svc 创建，另一个 svc 加载"""
    bus = EventBus()
    _, cand_svc, _ = factory_mod.build_services(str(tmp_path))
    tm = TaskManager(data_dir=tmp_path)
    ts = TaskService(tm)
    dm1 = DelegationManager(data_dir=tmp_path)
    ds1 = DelegationService(dm1, cand_svc, bus, ts)
    cand = cand_svc.submit({"candidate_name": "X"}, owner_agent_id="hh-A")
    d = ds1.create(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref=cand.id,
    )
    # 新实例
    dm2 = DelegationManager(data_dir=tmp_path)
    ds2 = DelegationService(dm2, cand_svc, bus, ts)
    assert ds2.get(d.id) is not None
    assert ds2.get(d.id).status == DelegationStatus.PENDING
