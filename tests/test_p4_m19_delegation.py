"""
P4 M19 测试 - Delegation 实体 + 状态机
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.collaboration.delegation import (
    Delegation, DelegationStatus, InvalidDelegationTransitionError
)
from zhongjie.domain.models import FeeShare, FeeShareValidationError


def test_delegation_default_state():
    d = Delegation(from_agent_id="hh-A", to_agent_id="hh-B",
                   candidate_ref="cand_1", jd_context="P7 数据岗")
    assert d.status == DelegationStatus.PENDING
    assert d.is_active()
    assert not d.is_terminal()
    assert d.visibility == "masked"


def test_delegation_lifecycle_happy_path():
    """完整流程: pending → accepted → in_progress → placed → settled"""
    d = Delegation(from_agent_id="hh-A", to_agent_id="hh-B",
                   candidate_ref="cand_1", jd_context="X")
    d.accept(actor="hh-B", note="我有金融客户")
    assert d.status == DelegationStatus.ACCEPTED
    assert d.decided_at is not None

    d.start_progress(actor="hh-B")
    assert d.status == DelegationStatus.IN_PROGRESS

    d.mark_placed(actor="hh-B")
    assert d.status == DelegationStatus.PLACED

    d.settle(actor="platform")
    assert d.status == DelegationStatus.SETTLED
    assert d.is_terminal()


def test_delegation_reject_path():
    d = Delegation(from_agent_id="hh-A", to_agent_id="hh-B",
                   candidate_ref="cand_1", jd_context="X")
    d.reject(actor="hh-B", reason="不擅长此岗")
    assert d.status == DelegationStatus.REJECTED
    assert d.is_terminal()


def test_delegation_cancel_path():
    d = Delegation(from_agent_id="hh-A", to_agent_id="hh-B",
                   candidate_ref="cand_1", jd_context="X")
    d.cancel(actor="hh-A", reason="候选人撤回")
    assert d.status == DelegationStatus.CANCELLED
    assert d.is_terminal()


def test_invalid_transition_raises():
    """PENDING → PLACED 非法（必须经过 accepted + in_progress）"""
    d = Delegation(from_agent_id="hh-A", to_agent_id="hh-B",
                   candidate_ref="cand_1")
    with pytest.raises(InvalidDelegationTransitionError):
        d.mark_placed()


def test_terminal_no_more_transitions():
    d = Delegation(from_agent_id="hh-A", to_agent_id="hh-B",
                   candidate_ref="cand_1")
    d.reject()
    with pytest.raises(InvalidDelegationTransitionError):
        d.accept()
    with pytest.raises(InvalidDelegationTransitionError):
        d.cancel()


def test_set_fee_split_validates():
    d = Delegation(from_agent_id="hh-A", to_agent_id="hh-B",
                   candidate_ref="cand_1")
    d.set_fee_split([
        FeeShare("hh-A", 0.4, role="owner"),
        FeeShare("hh-B", 0.5, role="co_finder"),
        FeeShare("platform", 0.1, role="platform_fee"),
    ])
    assert d.fee_share_for("hh-A").pct == 0.4
    assert d.fee_share_for("platform").role == "platform_fee"

    # 非法
    with pytest.raises(FeeShareValidationError):
        d.set_fee_split([FeeShare("hh-A", 0.5)])  # 不到 1.0


def test_state_history_recorded():
    d = Delegation(from_agent_id="hh-A", to_agent_id="hh-B",
                   candidate_ref="cand_1")
    d.accept(actor="hh-B", note="ok")
    d.start_progress(actor="hh-B")
    transitions = [(h.from_state, h.to_state) for h in d.history]
    assert transitions[0] == (DelegationStatus.PENDING, DelegationStatus.PENDING)
    assert transitions[1] == (DelegationStatus.PENDING, DelegationStatus.ACCEPTED)
    assert transitions[2] == (DelegationStatus.ACCEPTED, DelegationStatus.IN_PROGRESS)
    assert d.history[1].actor == "hh-B"


def test_delegation_round_trip():
    d = Delegation(
        from_agent_id="hh-A", to_agent_id="hh-B",
        candidate_ref="cand_1", jd_context="P7",
        task_id="task_1", deadline="2026-12-31",
        note="特殊关注",
    )
    d.set_fee_split([
        FeeShare("hh-A", 0.4), FeeShare("hh-B", 0.6),
    ])
    d.accept()
    d2 = Delegation.from_dict(d.to_dict())
    assert d2.id == d.id
    assert d2.status == DelegationStatus.ACCEPTED
    assert d2.fee_share_for("hh-A").pct == 0.4
    assert d2.task_id == "task_1"
    assert d2.deadline == "2026-12-31"
    assert d2.note == "特殊关注"


def test_delegation_from_legacy_dict():
    """老数据 (无 task_id, deadline) 正常加载"""
    legacy = {
        "id": "deleg_1",
        "from_agent_id": "hh-A", "to_agent_id": "hh-B",
        "candidate_ref": "cand_1", "jd_context": "X",
        "status": "pending", "visibility": "masked",
    }
    d = Delegation.from_dict(legacy)
    assert d.task_id is None
    assert d.status == DelegationStatus.PENDING
    assert d.fee_split == []


def test_all_delegation_states_exist():
    """7 个状态齐全"""
    states = {s.value for s in DelegationStatus}
    assert states == {
        "pending", "accepted", "rejected", "in_progress",
        "placed", "settled", "cancelled",
    }
