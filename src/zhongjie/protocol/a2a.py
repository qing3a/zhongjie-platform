"""
L6 Protocol - A2A Protocol 适配
对应交付物三的 P3 M16 + 交付物一的设计

A2A JSON-RPC 2.0 方法实现:
- tasks/send       (params: {id?, message, sessionId?}) → 提交/推进 Task
- tasks/get        (params: {id})                         → 查询 Task
- tasks/cancel     (params: {id})                         → 取消 Task
- message/send     (params: {message})                    → 无状态消息

响应包装: JSON-RPC 2.0 envelope {jsonrpc, id, result/error}
业务层 result 用我们的统一格式 {status, code, data, message, meta}
"""
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ..collaboration.task import InvalidTransitionError, Task, TaskState
from ..collaboration.task_manager import TaskManager
from ..utils import translate_state_error
from .dispatcher import ProtocolDispatcher
from .responses import skill_error, skill_pending, skill_success

logger = logging.getLogger(__name__)


# A2A JSON-RPC 错误码
A2A_ERROR_CODES = {
    "PARSE_ERROR": -32700,
    "INVALID_REQUEST": -32600,
    "METHOD_NOT_FOUND": -32601,
    "INVALID_PARAMS": -32602,
    "INTERNAL_ERROR": -32603,
    # A2A 自定义
    "TASK_NOT_FOUND": -32001,
    "TASK_NOT_CANCELABLE": -32002,
    "INVALID_TASK_STATE": -32003,
}


class A2ADispatcher(ProtocolDispatcher):
    """A2A Protocol 分发器

    实现 A2A 的 4 个核心方法: tasks/send, tasks/get, tasks/cancel, message/send
    每个方法通过 dispatch() 路由
    """

    def __init__(self, task_manager: TaskManager | None = None) -> None:
        self._tm = task_manager or TaskManager()
        self._handlers: dict[str, Callable[[dict, dict], dict]] = {
            "tasks/send": self._handle_tasks_send,
            "tasks/get": self._handle_tasks_get,
            "tasks/cancel": self._handle_tasks_cancel,
            "message/send": self._handle_message_send,
        }
        self._skills = [
            {"id": "delegate", "name": "委托候选人给其他猎头",
             "inputModes": ["application/json"], "outputModes": ["application/json"]},
            {"id": "candidate_sourcing", "name": "候选人寻访",
             "inputModes": ["application/json"], "outputModes": ["application/json"]},
            {"id": "jd_matching", "name": "JD 匹配",
             "inputModes": ["application/json"], "outputModes": ["application/json"]},
        ]

    def dispatch(self, request: dict, context: dict | None = None) -> dict:
        """A2A dispatch: {method, params, id} → JSON-RPC envelope"""
        jsonrpc_id = request.get("id") or f"req_{uuid.uuid4().hex[:8]}"
        method = request.get("method")
        params = request.get("params", {})

        if not method:
            return self._rpc_error(jsonrpc_id, A2A_ERROR_CODES["INVALID_REQUEST"],
                                   "Missing 'method'")

        handler = self._handlers.get(method)
        if handler is None:
            return self._rpc_error(jsonrpc_id, A2A_ERROR_CODES["METHOD_NOT_FOUND"],
                                   f"Unknown method: {method}")
        try:
            result = handler(params, context or {})
            return self._rpc_result(jsonrpc_id, result)
        except Exception as e:
            logger.exception(f"A2A method {method} failed")
            return self._rpc_error(jsonrpc_id, A2A_ERROR_CODES["INTERNAL_ERROR"], str(e))

    def list_skills(self) -> list[dict]:
        """列出本 dispatcher 暴露的所有 skills（A2A Agent Card 风格）"""
        return self._skills

    # ---------- A2A 方法实现 ----------
    def _handle_tasks_send(self, params: dict, context: dict) -> dict:
        """tasks/send: 提交或推进一个 Task
        params: {id?, message: {parts: [...]}, sessionId?}
        """
        task_id = params.get("id")
        message = params.get("message", {})
        session_id = params.get("sessionId")  # A2A 中 sessionId = context_id

        # 提取 message 的 parts（payload）
        parts = message.get("parts", [])
        payload: dict = {}
        for p in parts:
            if p.get("type") == "data":
                payload.update(p.get("data", {}))
            elif p.get("type") == "text":
                payload["_text"] = p.get("text", "")

        owner_agent_id = context.get("agent_id")

        if task_id:
            # 推进已有 task
            task = self._tm.get(task_id)
            if task is None:
                return skill_error("ERR_TASK_NOT_FOUND", f"Task '{task_id}' 不存在", http_status=404)
            err = translate_state_error(
                lambda: task.resume_from_input(actor=owner_agent_id)
                if task.state == TaskState.INPUT_REQUIRED
                else task.start_working(actor=owner_agent_id)
            )
            if err is not None:
                return err
            self._tm._persist()
            return skill_success("A2A_TASK_RESUMED", task.to_dict(), "Task 推进")

        # 新建 task
        task = Task(
            context_id=session_id or f"ctx_{uuid.uuid4().hex[:8]}",
            kind=payload.get("skill", "unknown"),
            payload=payload,
            owner_agent_id=owner_agent_id,
        )
        self._tm.create(task)
        # 默认进入 working（业务 handler 可在后续 transition）
        err = translate_state_error(
            lambda: task.start_working(actor=owner_agent_id)
        )
        if err is not None:
            return err
        self._tm._persist()
        return skill_pending("A2A_TASK_CREATED", task.to_dict(), "Task 已创建并开始工作")

    def _handle_tasks_get(self, params: dict, context: dict) -> dict:
        """tasks/get: 查询 Task 状态
        params: {id}
        """
        task_id = params.get("id")
        if not task_id:
            return skill_error("ERR_MISSING_PARAM", "Missing 'id'")
        task = self._tm.get(task_id)
        if task is None:
            return skill_error("ERR_TASK_NOT_FOUND", f"Task '{task_id}' 不存在", http_status=404)
        return skill_success("A2A_TASK_FETCHED", task.to_dict(), "Task 状态已获取")

    def _handle_tasks_cancel(self, params: dict, context: dict) -> dict:
        """tasks/cancel: 取消 Task
        params: {id}
        """
        task_id = params.get("id")
        if not task_id:
            return skill_error("ERR_MISSING_PARAM", "Missing 'id'")
        task = self._tm.get(task_id)
        if task is None:
            return skill_error("ERR_TASK_NOT_FOUND", f"Task '{task_id}' 不存在", http_status=404)
        if task.is_terminal():
            return skill_error("ERR_TASK_NOT_CANCELABLE",
                               f"Task 已处于终态: {task.state.value}")
        actor = context.get("agent_id")
        task.cancel(actor=actor, reason="通过 A2A 协议取消")
        self._tm._persist()
        return skill_success("A2A_TASK_CANCELED", task.to_dict(), "Task 已取消")

    def _handle_message_send(self, params: dict, context: dict) -> dict:
        """message/send: 无状态消息（不创建 Task）
        params: {message: {parts: [...]}}
        """
        message = params.get("message", {})
        parts = message.get("parts", [])
        payload: dict = {}
        for p in parts:
            if p.get("type") == "data":
                payload.update(p.get("data", {}))
        # 无状态：直接返回 ack
        return skill_success("A2A_MESSAGE_RECEIVED",
                            {"echo": payload, "received_at": _now_iso()},
                            "消息已接收（无状态）")

    # ---------- JSON-RPC envelope ----------
    @staticmethod
    def _rpc_result(jsonrpc_id: Any, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": jsonrpc_id, "result": result}

    @staticmethod
    def _rpc_error(jsonrpc_id: Any, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0", "id": jsonrpc_id,
            "error": {"code": code, "message": message},
        }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
