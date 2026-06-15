"""
L6 Protocol - A2A JSON-RPC 端点
端点:
- POST /a2a                      - JSON-RPC 2.0 主入口
- GET  /.well-known/agent-card.json - 平台 Agent Card
"""
from fastapi import APIRouter, Depends

from ...protocol.a2a import A2ADispatcher
from ..deps import get_task_manager

router = APIRouter(tags=["a2a"])


def get_a2a_dispatcher() -> A2ADispatcher:
    return A2ADispatcher(task_manager=get_task_manager())


@router.post("/a2a")
def a2a_endpoint(
    body: dict,
    dispatcher: A2ADispatcher = Depends(get_a2a_dispatcher),
):
    """A2A JSON-RPC 2.0 入口
    Body: {jsonrpc: "2.0", id: ..., method: "tasks/send", params: {...}}
    """
    context = {}  # TODO: 从 token 拿 agent_id
    return dispatcher.dispatch(body, context)


@router.get("/.well-known/agent-card.json")
def well_known_agent_card():
    """A2A 标准: 平台自身的 Agent Card"""
    return {
        "name": "中介 API 平台 (zhongjie)",
        "description": "Agent 协作网络 - 猎头间委托/分润",
        "version": "1.0.0",
        "capabilities": {"streaming": True, "pushNotifications": True},
        "skills": [
            {"id": "delegate", "name": "委托候选人给其他猎头"},
            {"id": "candidate_sourcing", "name": "候选人寻访"},
            {"id": "jd_matching", "name": "JD 匹配"},
        ],
        "authentication": {"schemes": ["bearer"]},
    }
