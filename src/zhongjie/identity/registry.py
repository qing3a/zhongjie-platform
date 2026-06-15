"""
L2 Identity - AgentRegistry
Agent 的注册、查询、信任分调整、状态管理
对应交付物三的 M7
"""
import json
import logging
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any

from .agent_card import AgentCard, AgentRole, AgentStatus

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Agent 注册表
    - 内存 dict 索引（按 agent_id）
    - JSON 持久化（data/agents.json）
    - 线程安全（Lock 保护）
    """

    def __init__(self, data_dir: str | Path = "data", filename: str = "agents.json") -> None:
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / filename
        self._agents: dict[str, AgentCard] = {}
        self._lock = Lock()
        self._load()

    # ---------- 注册 ----------
    def register(self, card: AgentCard | dict) -> AgentCard:
        """注册一个新 Agent
        已存在同 agent_id 则覆盖（用于更新）
        """
        if isinstance(card, dict):
            card = AgentCard.from_dict(card)
        with self._lock:
            self._agents[card.agent_id] = card
            self._persist()
        logger.info(f"Agent 注册: {card.agent_id} ({card.name}, {card.role.value})")
        return card

    # ---------- 查询 ----------
    def get(self, agent_id: str) -> AgentCard | None:
        with self._lock:
            return self._agents.get(agent_id)

    def has(self, agent_id: str) -> bool:
        with self._lock:
            return agent_id in self._agents

    def find_by_name(self, name: str) -> AgentCard | None:
        """按名字查（不保证唯一，名字可能重复）"""
        with self._lock:
            for a in self._agents.values():
                if a.name == name:
                    return a
            return None

    def find_by_endpoint(self, endpoint: str) -> AgentCard | None:
        with self._lock:
            for a in self._agents.values():
                if a.endpoint == endpoint:
                    return a
            return None

    def list_all(self) -> list[AgentCard]:
        with self._lock:
            return list(self._agents.values())

    def list_by_role(self, role: AgentRole) -> list[AgentCard]:
        with self._lock:
            return [a for a in self._agents.values() if a.role == role]

    def list_by_capability(self, capability: str) -> list[AgentCard]:
        """按能力筛选（Agent 必须具备该能力 + ACTIVE 状态）"""
        with self._lock:
            return [
                a for a in self._agents.values()
                if capability in a.capabilities and a.is_active()
            ]

    def list_active(self) -> list[AgentCard]:
        with self._lock:
            return [a for a in self._agents.values() if a.is_active()]

    # ---------- 状态管理 ----------
    def suspend(self, agent_id: str, reason: str = "") -> bool:
        with self._lock:
            a = self._agents.get(agent_id)
            if not a:
                return False
            a.suspend()
            self._persist()
        logger.info(f"Agent 暂停: {agent_id} ({reason})")
        return True

    def activate(self, agent_id: str) -> bool:
        with self._lock:
            a = self._agents.get(agent_id)
            if not a:
                return False
            a.activate()
            self._persist()
        return True

    def revoke(self, agent_id: str) -> bool:
        with self._lock:
            a = self._agents.get(agent_id)
            if not a:
                return False
            a.revoke()
            self._persist()
        logger.info(f"Agent 吊销: {agent_id}")
        return True

    # ---------- 信任分 ----------
    def update_trust(self, agent_id: str, delta: float) -> float | None:
        """调整信任分，返回新分值；agent 不存在则返回 None"""
        with self._lock:
            a = self._agents.get(agent_id)
            if not a:
                return None
            new_score = a.update_trust(delta)
            self._persist()
        return new_score

    # ---------- 持久化 ----------
    def _persist(self) -> None:
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            data = [a.to_dict() for a in self._agents.values()]
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._path)
        except Exception as e:
            logger.warning(f"agents 持久化失败: {e}")

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            with self._lock:
                for item in raw:
                    if isinstance(item, dict) and "agent_id" in item:
                        card = AgentCard.from_dict(item)
                        self._agents[card.agent_id] = card
            logger.info(f"[Registry] 加载 {len(self._agents)} 个 Agent")
        except Exception as e:
            logger.warning(f"agents 加载失败: {e}")

    def count(self) -> int:
        with self._lock:
            return len(self._agents)
