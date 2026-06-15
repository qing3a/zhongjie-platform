"""
L6 Protocol - Task 路由
端点:
- POST   /api/tasks                - 创建 Task
- GET    /api/tasks                - 列出
- GET    /api/tasks/{task_id}      - 查单个
- POST   /api/tasks/{task_id}/complete - 完成
- POST   /api/tasks/{task_id}/fail    - 标记失败
- POST   /api/tasks/{task_id}/cancel  - 取消
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from ...collaboration.task import TaskState
from ...collaboration.task_service import TaskService
from ..deps import get_task_service
from ..schemas import TaskResponse, TaskSendRequest


def _to_response(t) -> TaskResponse:
    return TaskResponse(
        task_id=t.task_id,
        context_id=t.context_id,
        state=t.state.value,
        kind=t.kind,
        owner_agent_id=t.owner_agent_id,
        payload=t.payload,
        history=[
            {
                "from_state": h.from_state.value,
                "to_state": h.to_state.value,
                "timestamp": h.timestamp,
                "actor": h.actor,
                "note": h.note,
            }
            for h in t.history
        ],
        result=t.result,
        error=t.error,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(
    body: TaskSendRequest,
    owner_agent_id: str | None = None,
    ts: TaskService = Depends(get_task_service),
):
    t = ts.create(
        kind=body.kind, payload=body.payload,
        context_id=body.context_id, owner_agent_id=owner_agent_id,
    )
    return _to_response(t)


@router.get("", response_model=list[TaskResponse])
def list_tasks(
    state: str | None = None,
    owner_agent_id: str | None = None,
    context_id: str | None = None,
    ts: TaskService = Depends(get_task_service),
):
    if state:
        tasks = ts._tm.list_by_state(TaskState(state))
    elif owner_agent_id:
        tasks = ts._tm.list_by_owner(owner_agent_id)
    elif context_id:
        tasks = ts._tm.list_by_context(context_id)
    else:
        tasks = ts._tm.list_all()
    return [_to_response(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, ts: TaskService = Depends(get_task_service)):
    t = ts.get(task_id)
    if t is None:
        raise HTTPException(404, f"Task '{task_id}' 不存在")
    return _to_response(t)


@router.post("/{task_id}/complete", response_model=TaskResponse)
def complete_task(
    task_id: str,
    result: dict | None = None,
    actor: str | None = None,
    ts: TaskService = Depends(get_task_service),
):
    try:
        t = ts.complete(task_id, result=result, actor=actor)
    except Exception as e:
        raise HTTPException(400, str(e))
    return _to_response(t)


@router.post("/{task_id}/fail", response_model=TaskResponse)
def fail_task(
    task_id: str,
    error: str = "task failed",
    actor: str | None = None,
    ts: TaskService = Depends(get_task_service),
):
    try:
        t = ts.fail(task_id, error=error, actor=actor)
    except Exception as e:
        raise HTTPException(400, str(e))
    return _to_response(t)


@router.post("/{task_id}/cancel", response_model=TaskResponse)
def cancel_task(
    task_id: str,
    actor: str | None = None,
    reason: str = "",
    ts: TaskService = Depends(get_task_service),
):
    try:
        t = ts.cancel(task_id, actor=actor, reason=reason)
    except Exception as e:
        raise HTTPException(400, str(e))
    return _to_response(t)
