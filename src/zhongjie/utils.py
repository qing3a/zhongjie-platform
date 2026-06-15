"""
横切工具 (cross-cutting utilities)

不属于 L1-L6 任何一层, 但被多个层复用。

提供的工具:
- SKILL_LINK_VERSION: 协议版本常量, 升级时改这一处即可
- build_skill_response: Skill Link 统一响应格式的 builder (status/code/data/message/meta)
  - 是 protocol/responses.py 的事实底层
  - 不依赖 protocol 包, 横切
- translate_state_error: 把状态机异常翻译为业务错误响应, 默认适配 Skill Link 格式,
  也可注入自定义 error_factory 用于非 Skill Link 场景
"""
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Final, Literal

from .collaboration.task import InvalidTransitionError


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# Skill Link 协议版本 (bump 时改这一处)
SKILL_LINK_VERSION: Final[str] = "1.1"

# Skill Link 响应中合法的 status 值
SkillStatus = Literal["success", "error", "pending"]


def build_skill_response(
    status: SkillStatus,
    code: str,
    message: str = "",
    data: Any = None,
    *,
    http_status: int | None = None,
    version: str = SKILL_LINK_VERSION,
) -> dict:
    """构建 Skill Link 统一响应 dict

    形状 (README/API.md 定义的协议):
        {
            "status": "success" | "error" | "pending",
            "code":   "<业务码或错误码>",
            "data":   <payload> | None,
            "message": "<说明>",
            "meta":   {"timestamp": "...", ...}
        }

    meta 字段:
    - success / pending: 总是含 "version" (默认 SKILL_LINK_VERSION)
    - error: 总是含 "http_status" (默认 400)
    """
    meta: dict = {"timestamp": _now_iso()}
    if status == "error":
        meta["http_status"] = http_status if http_status is not None else 400
    else:
        meta["version"] = version
    return {
        "status": status,
        "code": code,
        "data": data,
        "message": message,
        "meta": meta,
    }


def _default_state_error(message: str) -> dict:
    """默认业务错误响应: Skill Link 格式, status=error / code=ERR_INVALID_STATE / http_status=409"""
    return build_skill_response("error", "ERR_INVALID_STATE", message=message, http_status=409)


def translate_state_error(
    op: Callable[[], Any],
    *,
    error_factory: Callable[[str], dict] | None = None,
) -> dict | None:
    """调用一个状态变更操作, 把 InvalidTransitionError 翻译为业务错误响应

    用法:
        err = translate_state_error(lambda: task.start_working(actor=owner))
        if err is not None:
            return err
        # 成功, 继续

    返回:
        None - 操作成功, 调用方继续
        dict - 业务错误响应, 调用方直接 return

    其他异常 (KeyError / ValueError 等) 不捕获, 上抛给调用方
    (通常会进入外层 dispatch / try-except 翻译为 INTERNAL_ERROR)。
    """
    factory = error_factory or _default_state_error
    try:
        op()
    except InvalidTransitionError as e:
        return factory(str(e))
    return None
