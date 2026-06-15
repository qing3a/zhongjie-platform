"""
L6 Protocol - Candidate 路由（demo 与生产都用）
端点:
- POST /api/candidates           - 创建候选人
- GET  /api/candidates           - 列出
- GET  /api/candidates/{id}      - 查单个
- POST /api/candidates/{id}/share  - 分享给 agent
- POST /api/candidates/{id}/unshare - 取消分享
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from ...domain.services import (
    CandidateNotFoundError, CandidateService, OwnerMismatchError
)
from ..deps import build_domain_services
from ..schemas import AgentRegisterRequest  # 复用

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


def _get_candidate_service() -> CandidateService:
    _, cand_svc, _ = build_domain_services()
    return cand_svc


@router.post("", status_code=201)
def create_candidate(
    body: dict,
    owner_agent_id: str = Query(..., description="拥有者 agent_id"),
    cs: CandidateService = Depends(_get_candidate_service),
):
    """提交候选人（自动脱敏）"""
    cand = cs.submit(body, owner_agent_id=owner_agent_id)
    return {
        "candidate_id": cand.id,
        "name": cand.candidate_name,  # 已脱敏
        "phone": cand.phone,
        "email": cand.email,
        "owner_agent_id": cand.owner_agent_id,
        "status": cand.status,
    }


@router.get("")
def list_candidates(
    owner_agent_id: str | None = None,
    cs: CandidateService = Depends(_get_candidate_service),
):
    cands = cs.list_all()
    if owner_agent_id:
        cands = [c for c in cands if c.owner_agent_id == owner_agent_id]
    return [
        {
            "candidate_id": c.id, "name": c.candidate_name,
            "phone": c.phone, "email": c.email,
            "owner_agent_id": c.owner_agent_id, "status": c.status,
        } for c in cands
    ]


@router.get("/{candidate_id}")
def get_candidate(
    candidate_id: str,
    cs: CandidateService = Depends(_get_candidate_service),
):
    c = cs.get(candidate_id)
    if c is None:
        raise HTTPException(404, f"候选人 '{candidate_id}' 不存在")
    return {
        "candidate_id": c.id, "name": c.candidate_name,
        "phone": c.phone, "email": c.email,
        "owner_agent_id": c.owner_agent_id,
        "shared_with": c.shared_with,
        "visibility": c.visibility,
        "provenance": c.provenance,
    }


@router.post("/{candidate_id}/share")
def share_candidate(
    candidate_id: str,
    target_agent_id: str = Query(...),
    actor_agent_id: str = Query(..., description="操作者（应为 owner）"),
    cs: CandidateService = Depends(_get_candidate_service),
):
    success, err = cs.share_to(actor_agent_id, candidate_id, target_agent_id)
    if not success:
        code_map = {
            "ERR_NOT_OWNER": 403,
            "ERR_CANDIDATE_NOT_FOUND": 404,
            "ERR_SELF_SHARE": 400,
        }
        raise HTTPException(code_map.get(err, 400), err)
    return {"ok": True, "candidate_id": candidate_id, "shared_with": target_agent_id}


@router.post("/{candidate_id}/unshare")
def unshare_candidate(
    candidate_id: str,
    target_agent_id: str = Query(...),
    actor_agent_id: str = Query(...),
    cs: CandidateService = Depends(_get_candidate_service),
):
    success, err = cs.unshare(actor_agent_id, candidate_id, target_agent_id)
    if not success:
        code_map = {"ERR_NOT_OWNER": 403, "ERR_CANDIDATE_NOT_FOUND": 404}
        raise HTTPException(code_map.get(err, 400), err)
    return {"ok": True, "candidate_id": candidate_id, "unshared": target_agent_id}
