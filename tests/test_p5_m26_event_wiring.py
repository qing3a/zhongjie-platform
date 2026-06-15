"""
回归测试：TrustStrategy 自动 wire / task.completed payload / A2A 错误不静默

针对以下修复:
- app.py 启动时强制初始化 TrustStrategy, 让其订阅 EventBus
- task_service.complete/fail payload 补 owner_agent_id
- protocol/a2a.py 不再静默吞 start_working 异常
- identity/auth.py 从根目录迁入 src 包
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


# ==================== A: TrustStrategy 自动 wire ====================

def test_trust_strategy_attached_on_lifespan_startup():
    """TrustStrategy 应在 app lifespan 启动阶段就被 attach, 不必等 /api/agents/{id}/trust"""
    from zhongjie.api import deps

    # 模拟 lifespan startup 触发的初始化
    deps.get_event_bus()
    deps.get_agent_registry()
    ts = deps.get_trust_strategy()

    assert ts._subscribed is True
    assert ts._bus is not None

    # 验证 handler 真的注册了
    bus = deps.get_event_bus()
    handlers_on_wildcard = bus._subscribers.get("*", [])
    assert any(h.__qualname__ == "TrustStrategy._on_event" for h in handlers_on_wildcard)


def test_trust_strategy_responds_to_delegation_accepted():
    """委托 accepted 事件应触发 trust 调整 (不再被吞)"""
    from zhongjie.api import deps
    from zhongjie.identity.agent_card import AgentCard, AgentRole

    deps.get_trust_strategy()  # wire
    reg = deps.get_agent_registry()
    a = reg.register(AgentCard(name="A", role=AgentRole.HEADHUNTER))
    b = reg.register(AgentCard(name="B", role=AgentRole.HEADHUNTER))

    before_a = reg.get(a.agent_id).trust_score
    before_b = reg.get(b.agent_id).trust_score

    # 模拟 DelegationService.accept 发的事件 (payload 只有 actor, 但 actor == to_agent_id)
    deps.get_event_bus().emit("delegation.accepted",
        payload={"delegation_id": "deleg_x", "actor": b.agent_id}, source="test")

    after_a = reg.get(a.agent_id).trust_score
    after_b = reg.get(b.agent_id).trust_score
    # B 应得 +0.05
    assert abs(after_b - (before_b + 0.05)) < 1e-9, f"B should +0.05: {before_b} -> {after_b}"


def test_trust_strategy_responds_to_delegation_placed():
    """委托 placed 事件应同时影响 from + to"""
    from zhongjie.api import deps
    from zhongjie.identity.agent_card import AgentCard, AgentRole

    deps.get_trust_strategy()
    reg = deps.get_agent_registry()
    a = reg.register(AgentCard(name="A", role=AgentRole.HEADHUNTER))
    b = reg.register(AgentCard(name="B", role=AgentRole.HEADHUNTER))

    deps.get_event_bus().emit("delegation.placed",
        payload={"delegation_id": "x",
                 "from_agent_id": a.agent_id,
                 "to_agent_id": b.agent_id}, source="test")

    # from +0.10, to +0.20
    assert abs(reg.get(a.agent_id).trust_score - 0.60) < 1e-9
    assert abs(reg.get(b.agent_id).trust_score - 0.70) < 1e-9


def test_trust_strategy_responds_to_task_completed_with_owner():
    """task.completed payload 含 owner_agent_id, 应被策略拾取"""
    from zhongjie.api import deps
    from zhongjie.identity.agent_card import AgentCard, AgentRole

    deps.get_trust_strategy()
    reg = deps.get_agent_registry()
    a = reg.register(AgentCard(name="A", role=AgentRole.HEADHUNTER))
    before = reg.get(a.agent_id).trust_score

    # 模拟修复后 TaskService.complete 发的 payload
    deps.get_event_bus().emit("task.completed",
        payload={"task_id": "t1", "result": None,
                 "owner_agent_id": a.agent_id, "actor": a.agent_id},
        source="test")

    assert abs(reg.get(a.agent_id).trust_score - (before + 0.02)) < 1e-9


# ==================== B: auth.py 迁移到 src 包 ====================

def test_auth_module_importable_from_new_path():
    from zhongjie.identity.auth import (
        APIKey, APIKeyManager, PERMISSIONS, ROLES, ROLE_LEVELS, Token,
        check_permission, get_current_token, has_permission, require_permission,
        require_role, token_header,
    )
    # 老 API 仍在
    assert hasattr(APIKeyManager, "generate_key_pair")
    assert "admin" in ROLE_LEVELS


def test_auth_functional_equivalence_to_old():
    """新 auth.py 与老 auth.py 行为一致 (key 生成 + 验签 + 角色)"""
    from zhongjie.identity.auth import APIKeyManager, check_permission, has_permission

    km = APIKeyManager()
    result = km.generate_key_pair(name="猎头A", role="requester",
                                    permissions=["headhunter_submit_jd"])
    assert result["key_id"].startswith("ak_")
    assert len(result["secret"]) == 16

    token = km.verify_token(result["token"])
    assert token is not None
    assert token.role == "requester"
    # admin 拥有所有权限
    assert has_permission(token, "platform_approve") is False
    assert has_permission(token, "headhunter_submit_jd") is True
    # 角色层级
    assert check_permission(token, "approver") is False
    assert check_permission(token, "viewer") is True

    # HMAC 签名
    import time
    ts = str(int(time.time()))
    import hmac, hashlib
    sig = hmac.new(
        km.keys[result["key_id"]].key_hash.encode(),
        f"{result['key_id']}_{ts}_".encode(), hashlib.sha256,
    ).hexdigest()
    assert km.verify_signature(result["key_id"], sig, ts, "") is True


def test_token_agent_id_real_time_sync_with_key():
    """Bug 6 修复: Token.agent_id 必须实时从 key 同步, 不能"只填不覆盖"
    场景: key 创建时绑 agent-A, 之后管理员把 key 重绑到 agent-B,
    老 token 仍应能操作但必须以 agent-B 身份 (key 是身份唯一权威)
    """
    from zhongjie.identity.auth import APIKeyManager

    km = APIKeyManager()

    # 1. key 绑定 agent-A, 生成 token
    r1 = km.generate_key_pair(name="K1", role="requester", agent_id="agent-A")
    t1 = km.verify_token(r1["token"])
    assert t1.agent_id == "agent-A"

    # 2. 模拟 key 重绑到 agent-B (业务场景: key 转给别人)
    km.keys[r1["key_id"]].agent_id = "agent-B"

    # 3. 用同一个 token 再次 verify → 必须读到 agent-B
    t1_again = km.verify_token(r1["token"])
    assert t1_again is not None
    assert t1_again.agent_id == "agent-B", (
        f"Token.agent_id 应实时从 key 同步, 但仍是 {t1_again.agent_id}"
    )


def test_token_agent_id_sync_when_key_clears_binding():
    """key.agent_id 被清空时, token.agent_id 也应清空 (key 是唯一权威)"""
    from zhongjie.identity.auth import APIKeyManager

    km = APIKeyManager()
    r = km.generate_key_pair(name="K", role="requester", agent_id="agent-A")
    t = km.verify_token(r["token"])
    assert t.agent_id == "agent-A"

    # 解除 key 的 agent 绑定 (None 表示"未绑任何 agent")
    km.keys[r["key_id"]].agent_id = None
    t2 = km.verify_token(r["token"])
    assert t2.agent_id is None


# ==================== C: A2A dispatcher 不再静默吞错 ====================

def test_a2a_dispatcher_no_silent_swallow_on_bad_initial_state():
    """A2ADispatcher._handle_tasks_send 新建 task 时, start_working 失败不再被吞
    模拟: 验证新建 task 一定是 SUBMITTED → WORKING 转换成功路径
    """
    from zhongjie.protocol.a2a import A2ADispatcher, A2A_ERROR_CODES
    from zhongjie.collaboration.task import TaskState
    from zhongjie.collaboration.task_manager import TaskManager
    import uuid, os, tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tm = TaskManager(data_dir=tmp)
        dispatcher = A2ADispatcher(task_manager=tm)

        req = {
            "jsonrpc": "2.0", "id": "1",
            "method": "tasks/send",
            "params": {"message": {"parts": [{"type": "data", "data": {"skill": "test"}}]}},
        }
        result = dispatcher.dispatch(req, context={})

        # 正常路径应返回 success, task 应在 WORKING
        assert "result" in result
        assert result["result"]["status"] == "pending"  # skill_pending status
        task_dict = result["result"]["data"]
        assert task_dict["state"] == TaskState.WORKING.value

        # 关键: 调用方能看到 task_id, 不再被静默错误吞掉
        assert task_dict["task_id"].startswith("task_")


def test_a2a_dispatcher_invalid_state_translation_to_business_error():
    """推进 task 时, InvalidTransitionError 翻译为业务码 (status=error, code=ERR_INVALID_STATE)
    而不是被吞, 也不是 INTERNAL_ERROR。
    """
    from zhongjie.protocol.a2a import A2ADispatcher
    from zhongjie.collaboration.task import TaskState
    from zhongjie.collaboration.task_manager import TaskManager
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tm = TaskManager(data_dir=tmp)
        dispatcher = A2ADispatcher(task_manager=tm)

        # 创建并立即把 task 推到终态
        from zhongjie.collaboration.task import Task
        t = Task(kind="x")
        t.start_working()  # SUBMITTED → WORKING
        t.complete()        # WORKING → COMPLETED 终态
        tm.create(t)

        # 试图推进一个终态 task → InvalidTransitionError
        req = {
            "jsonrpc": "2.0", "id": "1",
            "method": "tasks/send",
            "params": {"id": t.task_id,
                       "message": {"parts": [{"type": "data", "data": {}}]}},
        }
        result = dispatcher.dispatch(req, context={})

        # 业务错误: 顶层 result (JSON-RPC), 内层 status=error, code=ERR_INVALID_STATE
        assert "result" in result
        assert "error" not in result  # 不是 JSON-RPC 错误
        assert result["result"]["status"] == "error"
        assert result["result"]["code"] == "ERR_INVALID_STATE"
        # message 包含原 InvalidTransitionError 文本
        msg = result["result"]["message"]
        assert "completed" in msg or "COMPLETED" in msg
        assert "状态转换" in msg or "状态机" in msg or "transition" in msg.lower()


def test_a2a_dispatcher_new_task_invalid_initial_state_uses_business_code():
    """新建 task 路径: 手工构造非法初始状态时, 也走 ERR_INVALID_STATE 业务码
    (与推进路径保持一致), 不再上抛到 dispatch() 变 INTERNAL_ERROR
    """
    from zhongjie.protocol.a2a import A2ADispatcher
    from zhongjie.collaboration.task import Task, TaskState
    from zhongjie.collaboration.task_manager import TaskManager
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tm = TaskManager(data_dir=tmp)
        dispatcher = A2ADispatcher(task_manager=tm)

        # 注入一个初始就处于 WORKING 的 Task (非法: 跳过 SUBMITTED)
        # 然后让 _handle_tasks_send 走新建路径, start_working 会失败
        bad = Task(kind="x", state=TaskState.WORKING)
        tm.create(bad)
        # 注意: _handle_tasks_send 新建路径自己构造 Task, 不会复用上面的。
        # 改为 monkey-patch Task 构造来模拟非法初始状态
        import zhongjie.protocol.a2a as a2a_mod
        orig_task = a2a_mod.Task
        class BrokenTask(orig_task):
            def start_working(self, actor=None):
                from zhongjie.collaboration.task import InvalidTransitionError
                raise InvalidTransitionError(TaskState.FAILED, TaskState.WORKING)
        a2a_mod.Task = BrokenTask
        try:
            req = {
                "jsonrpc": "2.0", "id": "1",
                "method": "tasks/send",
                "params": {"message": {"parts": [{"type": "data", "data": {"skill": "x"}}]}},
            }
            result = dispatcher.dispatch(req, context={})
        finally:
            a2a_mod.Task = orig_task

        # 业务错误码, 与推进路径完全一致
        assert "result" in result
        assert "error" not in result
        assert result["result"]["status"] == "error"
        assert result["result"]["code"] == "ERR_INVALID_STATE"
        msg = result["result"]["message"]
        assert "状态转换" in msg or "transition" in msg.lower()


def test_translate_state_error_helper():
    """zhongjie.utils.translate_state_error 单元测试:
    - 成功路径: op 不抛错 → 返回 None
    - 业务错误路径: InvalidTransitionError → 返回默认 skill_error dict
    - 自定义 error_factory: 注入非 Skill Link 响应格式
    - 非业务错误: KeyError 等不捕获, 上抛
    """
    from zhongjie.collaboration.task import InvalidTransitionError, TaskState
    from zhongjie.utils import translate_state_error

    # 成功
    called = []
    assert translate_state_error(lambda: called.append(1)) is None
    assert called == [1]

    # 默认业务错误 (Skill Link 格式)
    def boom():
        raise InvalidTransitionError(TaskState.SUBMITTED, TaskState.COMPLETED)
    result = translate_state_error(boom)
    assert result is not None
    assert result["status"] == "error"
    assert result["code"] == "ERR_INVALID_STATE"
    assert result["meta"]["http_status"] == 409
    assert "状态转换" in result["message"] or "transition" in result["message"].lower()

    # 自定义 error_factory (非 Skill Link 场景)
    def custom_factory(msg: str) -> dict:
        return {"err": "STATE", "msg": msg}

    result = translate_state_error(boom, error_factory=custom_factory)
    assert result == {"err": "STATE", "msg": result["msg"]}
    # 验证默认 factory 不会被调到
    assert "status" not in result

    # 其他异常上抛 (不吞)
    def boom_key():
        return {}["missing"]
    with pytest.raises(KeyError):
        translate_state_error(boom_key)


def test_build_skill_response_shape_and_meta_variants():
    """build_skill_response: 单一事实来源, 被 protocol/responses.py 复用
    - success/pending → meta 含 version + timestamp
    - error → meta 含 http_status + timestamp
    - 默认 version 来自 SKILL_LINK_VERSION 常量 (bump 时只改一处)
    """
    from zhongjie.utils import SKILL_LINK_VERSION, build_skill_response

    # success
    r = build_skill_response("success", "OK", data={"x": 1}, message="done")
    assert r["status"] == "success"
    assert r["code"] == "OK"
    assert r["data"] == {"x": 1}
    assert r["message"] == "done"
    assert "version" in r["meta"] and r["meta"]["version"] == SKILL_LINK_VERSION
    assert "timestamp" in r["meta"]
    assert "http_status" not in r["meta"]

    # pending
    r = build_skill_response("pending", "WAIT")
    assert r["status"] == "pending"
    assert r["code"] == "WAIT"
    assert "version" in r["meta"] and "http_status" not in r["meta"]

    # error 默认 http_status=400
    r = build_skill_response("error", "E", message="oops")
    assert r["status"] == "error"
    assert r["code"] == "E"
    assert r["message"] == "oops"
    assert r["meta"]["http_status"] == 400
    assert "version" not in r["meta"]

    # error 自定义 http_status
    r = build_skill_response("error", "E", message="oops", http_status=409)
    assert r["meta"]["http_status"] == 409

    # 自定义 version 覆盖
    r = build_skill_response("success", "OK", version="2.0-beta")
    assert r["meta"]["version"] == "2.0-beta"


def test_protocol_responses_wrappers_match_utils_builder():
    """protocol/responses.py 的三个 wrapper 必须与 utils builder 输出一致
    (防漂移: 任何一边改了 meta 字段另一边会失败)
    """
    from zhongjie.protocol.responses import skill_error, skill_pending, skill_success
    from zhongjie.utils import build_skill_response

    assert skill_success("C", data=1, message="m") == build_skill_response(
        "success", "C", data=1, message="m",
    )
    assert skill_error("C", "m", http_status=422) == build_skill_response(
        "error", "C", message="m", http_status=422,
    )
    assert skill_pending("C", data=[]) == build_skill_response(
        "pending", "C", data=[],
    )


# ==================== D: task.completed payload 完整性 ====================

def test_task_service_complete_payload_contains_owner():
    """TaskService.complete 发出的 task.completed payload 必须含 owner_agent_id"""
    from zhongjie.collaboration.task_service import TaskService
    from zhongjie.collaboration.task_manager import TaskManager
    from zhongjie.infra.events import EventBus
    import tempfile

    captured = []
    with tempfile.TemporaryDirectory() as tmp:
        bus = EventBus()
        bus.subscribe("task.completed", lambda e: captured.append(e.payload))
        tm = TaskManager(data_dir=tmp)
        ts = TaskService(tm, event_bus=bus)

        task = ts.create(kind="test", payload={}, owner_agent_id="agent-X")
        ts.complete(task.task_id, result={"ok": True})

        assert len(captured) == 1
        payload = captured[0]
        assert payload.get("owner_agent_id") == "agent-X"
        assert payload.get("actor") == "agent-X"  # 默认回退到 owner


def test_task_service_fail_payload_contains_owner():
    from zhongjie.collaboration.task_service import TaskService
    from zhongjie.collaboration.task_manager import TaskManager
    from zhongjie.infra.events import EventBus
    import tempfile

    captured = []
    with tempfile.TemporaryDirectory() as tmp:
        bus = EventBus()
        bus.subscribe("task.failed", lambda e: captured.append(e.payload))
        tm = TaskManager(data_dir=tmp)
        ts = TaskService(tm, event_bus=bus)

        task = ts.create(kind="test", payload={}, owner_agent_id="agent-Y")
        ts.fail(task.task_id, error="boom")

        assert len(captured) == 1
        assert captured[0].get("owner_agent_id") == "agent-Y"
        assert captured[0].get("error") == "boom"
