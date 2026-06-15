"""
L6 Protocol - Delegation 路由
端点:
- POST   /api/delegations                - 发起委托
- GET    /api/delegations                - 列出
- GET    /api/delegations/{id}           - 查单个
- POST   /api/delegations/{id}/accept    - 接受
- POST   /api/delegations/{id}/reject    - 拒绝
- POST   /api/delegations/{id}/cancel    - 取消
- POST   /api/delegations/{id}/place     - 标记入职
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from ...collaboration.delegation_service import (
    CandidateAlreadyDelegatedError, DelegationNotFoundError, DelegationService,
    PermissionError_ as DSError,
)
from ...domain.models import FeeShareValidationError
from ..deps import get_delegation_service
from ..schemas import DelegationCreateRequest, DelegationResponse


def _to_response(d) -> DelegationResponse:
    return DelegationResponse(
        id=d.id,
        task_id=d.task_id,
        from_agent_id=d.from_agent_id,
        to_agent_id=d.to_agent_id,
        candidate_ref=d.candidate_ref,
        jd_context=d.jd_context,
        status=d.status.value,
        fee_split=d.fee_split,
        visibility=d.visibility,
        deadline=d.deadline,
        created_at=d.created_at,
        decided_at=d.decided_at,
    )


router = APIRouter(prefix="/api/delegations", tags=["delegations"])


@router.post("", response_model=DelegationResponse, status_code=201)
def create_delegation(
    body: DelegationCreateRequest,
    ds: DelegationService = Depends(get_delegation_service),
):
    try:
        d = ds.create(
            from_agent_id=body.from_agent_id,
            to_agent_id=body.to_agent_id,
            candidate_ref=body.candidate_ref,
            jd_context=body.jd_context,
            fee_split=body.fee_split,
            visibility=body.visibility,
            deadline=body.deadline,
            note=body.note,
        )
    except FeeShareValidationError as e:
        raise HTTPException(400, f"fee_split 校验失败: {e}")
    except CandidateAlreadyDelegatedError as e:
        raise HTTPException(409, str(e))
    except (DSError, ValueError) as e:
        raise HTTPException(403, str(e))
    return _to_response(d)


@router.get("", response_model=list[DelegationResponse])
def list_delegations(
    agent_id: str | None = Query(None, description="按 agent 查 (from 或 to)"),
    role: str | None = Query(None, description="from / to / any"),
    status: str | None = None,
    ds: DelegationService = Depends(get_delegation_service),
):
    if agent_id:
        delegs = ds.list_for_agent(agent_id, role=role or "any")
    else:
        delegs = ds._dm.list_all()
    if status:
        delegs = [d for d in delegs if d.status.value == status]
    return [_to_response(d) for d in delegs]


@router.get("/{delegation_id}", response_model=DelegationResponse)
def get_delegation(delegation_id: str, ds: DelegationService = Depends(get_delegation_service)):
    d = ds.get(delegation_id)
    if d is None:
        raise HTTPException(404, f"委托 '{delegation_id}' 不存在")
    return _to_response(d)


@router.post("/{delegation_id}/accept", response_model=DelegationResponse)
def accept_delegation(
    delegation_id: str,
    actor: str = Query(..., description="受托方 agent_id"),
    note: str = "",
    ds: DelegationService = Depends(get_delegation_service),
):
    try:
        d = ds.accept(delegation_id, actor=actor, note=note)
    except DelegationNotFoundError:
        raise HTTPException(404, f"委托 '{delegation_id}' 不存在")
    except DSError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))
    return _to_response(d)


@router.post("/{delegation_id}/reject", response_model=DelegationResponse)
def reject_delegation(
    delegation_id: str,
    actor: str = Query(..., description="受托方 agent_id"),
    reason: str = "",
    ds: DelegationService = Depends(get_delegation_service),
):
    try:
        d = ds.reject(delegation_id, actor=actor, reason=reason)
    except DelegationNotFoundError:
        raise HTTPException(404, f"委托 '{delegation_id}' 不存在")
    except DSError as e:
        raise HTTPException(403, str(e))
    return _to_response(d)


@router.post("/{delegation_id}/cancel", response_model=DelegationResponse)
def cancel_delegation(
    delegation_id: str,
    actor: str = Query(..., description="任一参与方 agent_id"),
    reason: str = "",
    ds: DelegationService = Depends(get_delegation_service),
):
    try:
        d = ds.cancel(delegation_id, actor=actor, reason=reason)
    except DelegationNotFoundError:
        raise HTTPException(404, f"委托 '{delegation_id}' 不存在")
    except DSError as e:
        raise HTTPException(403, str(e))
    return _to_response(d)


@router.post("/{delegation_id}/place", response_model=DelegationResponse)
def mark_placed(
    delegation_id: str,
    actor: str = Query(..., description="受托方 agent_id"),
    ds: DelegationService = Depends(get_delegation_service),
):
    """标记入职
    简化: 自动经过 in_progress（如果还未），再 placed
    """
    try:
        d = ds.get(delegation_id)
        if d is None:
            raise HTTPException(404, f"委托 '{delegation_id}' 不存在")
        if d.status.value == "accepted":
            ds.start_progress(delegation_id, actor=actor)
        d = ds.mark_placed(delegation_id, actor=actor)
    except DelegationNotFoundError:
        raise HTTPException(404, f"委托 '{delegation_id}' 不存在")
    except Exception as e:
        raise HTTPException(400, str(e))
    return _to_response(d)
