"""
L6 Protocol - 审计路由
端点:
- GET /api/audit                - 列出（可按 agent/decision/trust 范围筛选）
- GET /api/audit/verify        - 校验链式 hash
- GET /api/audit/stats          - 统计
"""
from fastapi import APIRouter, Depends, Query

from ...governance.audit import AppendOnlyAuditLog
from ..deps import get_audit_log
from ..schemas import AuditEntryResponse


def _to_response(e) -> AuditEntryResponse:
    return AuditEntryResponse(
        id=e.id, request_id=e.request_id, owner_agent_id=e.owner_agent_id,
        decision=e.decision, matched_rule=e.matched_rule,
        trust_score=e.trust_score, timestamp=e.timestamp,
        hash=e.hash, prev_hash=e.prev_hash, note=e.note,
    )


router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntryResponse])
def list_audit(
    agent_id: str | None = None,
    decision: str | None = None,
    trust_low: float | None = None,
    trust_high: float | None = None,
    limit: int = Query(100, le=500),
    log: AppendOnlyAuditLog = Depends(get_audit_log),
):
    if agent_id:
        entries = log.by_agent(agent_id)
    elif decision:
        entries = log.by_decision(decision)
    elif trust_low is not None or trust_high is not None:
        entries = log.by_trust_range(low=trust_low, high=trust_high)
    else:
        entries = log.all()
    return [_to_response(e) for e in entries[-limit:]]


@router.get("/verify")
def verify_audit(log: AppendOnlyAuditLog = Depends(get_audit_log)):
    """校验链式 hash 完整性"""
    is_valid, issues = log.verify_integrity()
    return {"is_valid": is_valid, "issues": issues, "entry_count": log.count()}


@router.get("/stats")
def audit_stats(log: AppendOnlyAuditLog = Depends(get_audit_log)):
    return log.stats()
