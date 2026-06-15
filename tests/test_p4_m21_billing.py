"""
P4 M21 测试 - BillingService
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.domain.models import FeeShare
from zhongjie.infra.billing_service import BillingService, Invoice


@pytest.fixture
def bs(tmp_path):
    return BillingService(data_dir=tmp_path)


def test_create_invoice_splits_total(bs):
    """按 fee_split 拆账: 100000 元 + 0.4/0.5/0.1 → 40000/50000/10000"""
    inv = bs.create_invoice(
        delegation_id="deleg_1", candidate_ref="cand_1",
        total_amount=100000,
        fee_split=[
            FeeShare("hh-A", 0.4),
            FeeShare("hh-B", 0.5),
            FeeShare("platform", 0.1),
        ],
    )
    assert inv.total_amount == 100000
    assert len(inv.lines) == 3
    amounts = {l["agent_id"]: l["amount"] for l in inv.lines}
    assert amounts["hh-A"] == 40000.0
    assert amounts["hh-B"] == 50000.0
    assert amounts["platform"] == 10000.0


def test_create_invoice_rejects_empty_fee_split(bs):
    with pytest.raises(ValueError):
        bs.create_invoice("d1", "c1", 1000, [])


def test_create_invoice_rejects_negative_amount(bs):
    with pytest.raises(ValueError):
        bs.create_invoice("d1", "c1", -100, [FeeShare("x", 1.0)])


def test_settle_full_invoice(bs):
    inv = bs.create_invoice("d1", "c1", 1000,
                             [FeeShare("hh-A", 0.5), FeeShare("hh-B", 0.5)])
    settled = bs.settle(inv.id)
    assert settled.status == "settled"
    assert settled.is_settled()
    assert settled.settled_at is not None
    # 所有行已 settled
    for line in settled.lines:
        assert line["settled"] is True


def test_settle_single_line(bs):
    inv = bs.create_invoice("d1", "c1", 1000,
                             [FeeShare("hh-A", 0.5), FeeShare("hh-B", 0.5)])
    bs.settle_line(inv.id, "hh-A")
    # 仅 hh-A 已结算
    a_line = inv.line_for("hh-A")
    b_line = inv.line_for("hh-B")
    assert a_line["settled"] is True
    assert b_line["settled"] is False
    # 整体未全结
    assert inv.status == "pending"
    # 全结后状态变更
    bs.settle_line(inv.id, "hh-B")
    assert inv.status == "settled"


def test_settle_nonexistent_invoice_raises(bs):
    with pytest.raises(ValueError):
        bs.settle("inv_fake")


def test_list_for_agent(bs):
    inv1 = bs.create_invoice("d1", "c1", 1000, [FeeShare("hh-A", 0.5), FeeShare("hh-B", 0.5)])
    inv2 = bs.create_invoice("d2", "c2", 2000, [FeeShare("hh-A", 0.3), FeeShare("hh-B", 0.7)])
    # hh-A 涉及两张
    a_invs = bs.list_for_agent("hh-A")
    assert len(a_invs) == 2
    # hh-B 涉及两张
    b_invs = bs.list_for_agent("hh-B")
    assert len(b_invs) == 2
    # hh-C 不涉及
    c_invs = bs.list_for_agent("hh-C")
    assert len(c_invs) == 0


def test_settled_only_filter(bs):
    inv1 = bs.create_invoice("d1", "c1", 1000, [FeeShare("hh-A", 1.0)])
    inv2 = bs.create_invoice("d2", "c2", 1000, [FeeShare("hh-A", 1.0)])
    bs.settle(inv1.id)
    # 已结算: 1
    settled = bs.list_for_agent("hh-A", settled_only=True)
    assert len(settled) == 1
    # 全部: 2
    all_inv = bs.list_for_agent("hh-A", settled_only=False)
    assert len(all_inv) == 2


def test_total_paid_to(bs):
    bs.create_invoice("d1", "c1", 1000, [FeeShare("hh-A", 1.0)])
    bs.create_invoice("d2", "c2", 2000, [FeeShare("hh-A", 0.5), FeeShare("hh-B", 0.5)])
    # 未结算
    assert bs.total_paid_to("hh-A") == 0.0
    # 结算 d1
    inv1 = next(i for i in bs.list_for_agent("hh-A") if i.delegation_id == "d1")
    bs.settle(inv1.id)
    assert bs.total_paid_to("hh-A") == 1000.0


def test_total_pending_to(bs):
    bs.create_invoice("d1", "c1", 1000, [FeeShare("hh-A", 1.0)])
    bs.create_invoice("d2", "c2", 2000, [FeeShare("hh-A", 0.5), FeeShare("hh-B", 0.5)])
    # hh-A 应收: 1000 + 1000 = 2000 (含 d1/d2)
    assert bs.total_pending_to("hh-A") == 2000.0
    # 结算 d1
    inv1 = next(i for i in bs.list_for_agent("hh-A") if i.delegation_id == "d1")
    bs.settle(inv1.id)
    assert bs.total_pending_to("hh-A") == 1000.0  # d2 仍 pending


def test_list_by_delegation(bs):
    bs.create_invoice("d1", "c1", 1000, [FeeShare("hh-A", 1.0)])
    bs.create_invoice("d1", "c2", 2000, [FeeShare("hh-A", 1.0)])
    bs.create_invoice("d2", "c3", 3000, [FeeShare("hh-A", 1.0)])
    d1_invs = bs.list_by_delegation("d1")
    assert len(d1_invs) == 2


def test_persistence(tmp_path):
    bs1 = BillingService(data_dir=tmp_path)
    inv = bs1.create_invoice("d1", "c1", 1000, [FeeShare("hh-A", 1.0)])
    bs2 = BillingService(data_dir=tmp_path)
    assert bs2.get(inv.id) is not None
    assert bs2.get(inv.id).total_amount == 1000


def test_invoice_line_for(bs):
    inv = bs.create_invoice("d1", "c1", 1000, [FeeShare("hh-A", 0.4), FeeShare("hh-B", 0.6)])
    a = inv.line_for("hh-A")
    assert a["amount"] == 400.0
    assert inv.line_for("hh-Z") is None
