"""
L6 Protocol - Agent 管理路由
端点:
- POST   /api/agents                 - 注册 Agent
- GET    /api/agents                 - 列出所有
- GET    /api/agents/{agent_id}      - 查单个
- GET    /api/agents/{agent_id}/card - 导出 A2A Card
- DELETE /api/agents/{agent_id}      - 吊销
- POST   /api/agents/{agent_id}/trust - 调整信任分
"""
from fastapi import APIRouter, Depends, HTTPException

from ...identity.agent_card import AgentCard, AgentRole, AgentTier
from ...identity.registry import AgentRegistry
from ...identity.trust_strategy import TrustStrategy
from ..deps import get_agent_registry, get_trust_strategy
from ..schemas import (
    AgentListResponse, AgentRegisterRequest, AgentResponse,
    TrustAdjustRequest, TrustHistoryEntry,
)

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _to_response(card: AgentCard) -> AgentResponse:
    return AgentResponse(
        agent_id=card.agent_id, name=card.name, role=card.role.value,
        capabilities=card.capabilities, tier=card.tier.value,
        trust_score=card.trust_score, status=card.status.value,
        endpoint=card.endpoint, description=card.description,
        created_at=card.created_at,
    )


@router.post("", response_model=AgentResponse, status_code=201)
def register_agent(
    body: AgentRegisterRequest,
    reg: AgentRegistry = Depends(get_agent_registry),
):
    card = AgentCard(
        name=body.name, role=AgentRole(body.role), tier=AgentTier(body.tier),
        capabilities=body.capabilities, endpoint=body.endpoint,
        description=body.description,
    )
    reg.register(card)
    return _to_response(card)


@router.get("", response_model=AgentListResponse)
def list_agents(
    role: str | None = None,
    capability: str | None = None,
    only_active: bool = True,
    reg: AgentRegistry = Depends(get_agent_registry),
):
    if only_active:
        agents = reg.list_active()
    else:
        agents = reg.list_all()
    if role:
        agents = [a for a in agents if a.role.value == role]
    if capability:
        agents = [a for a in agents if capability in a.capabilities]
    by_role: dict[str, int] = {}
    for a in agents:
        by_role[a.role.value] = by_role.get(a.role.value, 0) + 1
    return AgentListResponse(
        agents=[_to_response(a) for a in agents],
        total=len(agents),
        by_role=by_role,
    )


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: str, reg: AgentRegistry = Depends(get_agent_registry)):
    card = reg.get(agent_id)
    if card is None:
        raise HTTPException(404, f"Agent '{agent_id}' 不存在")
    return _to_response(card)


@router.get("/{agent_id}/card")
def get_agent_card(agent_id: str, reg: AgentRegistry = Depends(get_agent_registry)):
    """导出 A2A Protocol 标准的 Agent Card"""
    card = reg.get(agent_id)
    if card is None or not card.is_active():
        raise HTTPException(404, f"Agent '{agent_id}' 不存在或未激活")
    return card.to_a2a_card()


@router.delete("/{agent_id}", status_code=204)
def revoke_agent(agent_id: str, reg: AgentRegistry = Depends(get_agent_registry)):
    if not reg.revoke(agent_id):
        raise HTTPException(404, f"Agent '{agent_id}' 不存在")
    return None


@router.post("/{agent_id}/trust", response_model=AgentResponse)
def adjust_trust(
    agent_id: str,
    body: TrustAdjustRequest,
    reg: AgentRegistry = Depends(get_agent_registry),
    strategy: TrustStrategy = Depends(get_trust_strategy),
):
    """手动调整信任分"""
    new_score = strategy.apply_manual(agent_id, body.delta, reason=body.reason)
    if new_score is None:
        raise HTTPException(404, f"Agent '{agent_id}' 不存在")
    card = reg.get(agent_id)
    return _to_response(card)


@router.get("/{agent_id}/trust/history", response_model=list[TrustHistoryEntry])
def get_trust_history(
    agent_id: str,
    strategy: TrustStrategy = Depends(get_trust_strategy),
):
    """查信任分调整历史"""
    history = strategy.history(agent_id=agent_id)
    return [
        TrustHistoryEntry(
            agent_id=h["agent_id"],
            event_type=h["event_type"],
            delta=h["delta"],
            new_score=h.get("new_score"),
            timestamp=h["timestamp"],
            reason=h.get("reason", ""),
        )
        for h in history
    ]
