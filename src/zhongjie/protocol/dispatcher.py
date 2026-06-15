"""
L6 Protocol - 协议分发抽象
为 P3 A2A 接入预留接口：未来 A2ADispatcher 实现同样的 Protocol 接口
"""
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any
import logging
import uuid

from ..domain.services import CandidateService, JDService, MatchService

logger = logging.getLogger(__name__)


class ProtocolDispatcher(ABC):
    """协议分发器抽象基类
    - 旧实现: LegacySkillLinkDispatcher (POST /skill/{name}/{action})
    - 新实现: A2ADispatcher (POST /a2a JSON-RPC) — 留 P3 实现
    """

    @abstractmethod
    def dispatch(self, request: dict, context: dict | None = None) -> dict:
        """分发一个请求，返回统一响应"""
        ...

    @abstractmethod
    def list_skills(self) -> list[dict]:
        """列出本 dispatcher 暴露的所有 skills"""
        ...


class SkillHandler(ABC):
    """单个 Skill 的处理器基类
    对应老 api_server.py:1339-1444 的 4 个猎头 skill handler
    """

    def __init__(self, jd_service: JDService, candidate_service: CandidateService, match_service: MatchService):
        self.jd = jd_service
        self.candidate = candidate_service
        self.match = match_service

    @property
    @abstractmethod
    def skill_name(self) -> str: ...

    @property
    @abstractmethod
    def actions(self) -> list[str]: ...

    @abstractmethod
    def handle(self, action: str, data: dict, context: dict | None = None) -> dict: ...
