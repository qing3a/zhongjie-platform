"""
L6 Protocol - 账单路由
端点:
- POST /api/billing/invoices      - 创建账单
- GET  /api/billing/invoices      - 列出
- GET  /api/billing/invoices/{id} - 查单个
- POST /api/billing/invoices/{id}/settle     - 整张结算
- POST /api/billing/invoices/{id}/settle_line - 单行结算
- GET  /api/billing/agents/{id}/summary       - 查 agent 收/欠汇总
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from ...infra.billing_service import BillingService
from ..deps import get_billing_service
from ..schemas import InvoiceCreateRequest, InvoiceResponse


def _to_response(inv) -> InvoiceResponse:
    return InvoiceResponse(
        id=inv.id, delegation_id=inv.delegation_id,
        candidate_ref=inv.candidate_ref, total_amount=inv.total_amount,
        currency=inv.currency, status=inv.status, lines=inv.lines,
        created_at=inv.created_at, settled_at=inv.settled_at,
    )


router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.post("/invoices", response_model=InvoiceResponse, status_code=201)
def create_invoice(
    body: InvoiceCreateRequest,
    bs: BillingService = Depends(get_billing_service),
):
    try:
        inv = bs.create_invoice(
            delegation_id=body.delegation_id,
            candidate_ref=body.candidate_ref,
            total_amount=body.total_amount,
            fee_split=body.fee_split,
            currency=body.currency,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _to_response(inv)


@router.get("/invoices", response_model=list[InvoiceResponse])
def list_invoices(
    agent_id: str | None = Query(None),
    delegation_id: str | None = Query(None),
    settled_only: bool = False,
    bs: BillingService = Depends(get_billing_service),
):
    if agent_id:
        invs = bs.list_for_agent(agent_id, settled_only=settled_only)
    elif delegation_id:
        invs = bs.list_by_delegation(delegation_id)
    else:
        invs = bs.list_all()
    return [_to_response(i) for i in invs]


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: str, bs: BillingService = Depends(get_billing_service)):
    inv = bs.get(invoice_id)
    if inv is None:
        raise HTTPException(404, f"Invoice '{invoice_id}' 不存在")
    return _to_response(inv)


@router.post("/invoices/{invoice_id}/settle", response_model=InvoiceResponse)
def settle_invoice(invoice_id: str, bs: BillingService = Depends(get_billing_service)):
    try:
        inv = bs.settle(invoice_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _to_response(inv)


@router.post("/invoices/{invoice_id}/settle_line", response_model=InvoiceResponse)
def settle_invoice_line(
    invoice_id: str,
    agent_id: str = Query(...),
    bs: BillingService = Depends(get_billing_service),
):
    try:
        inv = bs.settle_line(invoice_id, agent_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _to_response(inv)


@router.get("/agents/{agent_id}/summary")
def agent_summary(agent_id: str, bs: BillingService = Depends(get_billing_service)):
    """agent 的收/欠汇总"""
    return {
        "agent_id": agent_id,
        "total_paid": bs.total_paid_to(agent_id),
        "total_pending": bs.total_pending_to(agent_id),
    }
