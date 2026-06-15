"""
Skill Link 统一响应格式
对应老 api_server.py:760-779 SkillErrorCode + skill_success/skill_error/skill_pending

实现细节: 委托给 zhongjie.utils.build_skill_response (横切 builder),
本模块保留薄包装 + ErrorCode 常量类以便业务层调用。
"""
from typing import Any

from ..utils import build_skill_response


# 错误码定义 (从老 api_server.py 抽出)
class ErrorCode:
    # 通用
    ERR_MISSING_PARAM = "ERR_MISSING_PARAM"
    ERR_NOT_FOUND = "ERR_NOT_FOUND"
    ERR_INTERNAL = "ERR_INTERNAL"
    # 业务
    JD_SUBMITTED = "JD_SUBMITTED"
    CANDIDATE_SUBMITTED = "CANDIDATE_SUBMITTED"
    REQUEST_PENDING = "REQUEST_PENDING"
    MATCH_STATUS_FETCHED = "MATCH_STATUS_FETCHED"
    MATCH_SUBMITTED = "MATCH_SUBMITTED"
    # 治理
    REQUEST_SUBMITTED = "REQUEST_SUBMITTED"
    REQUEST_APPROVED = "REQUEST_APPROVED"
    REQUEST_REJECTED = "REQUEST_REJECTED"


def skill_success(code: str, data: Any = None, message: str = "") -> dict:
    """成功响应"""
    return build_skill_response("success", code, message=message, data=data)


def skill_error(code: str, message: str, http_status: int = 400) -> dict:
    """错误响应"""
    return build_skill_response("error", code, message=message, http_status=http_status)


def skill_pending(code: str, data: Any = None, message: str = "") -> dict:
    """待处理响应（异步场景）"""
    return build_skill_response("pending", code, message=message, data=data)
