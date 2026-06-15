"""
L2 Identity - Trust Score 策略（事件驱动）
对应 P5 M23

通过订阅 EventBus 上的关键事件，自动调整 agent 的 trust_score:
- delegation.placed       → from +0.1, to +0.2
- delegation.accepted     → to +0.05
- delegation.cancelled    → actor -0.05
- task.completed          → owner +0.02
- task.failed             → owner -0.05
- security.suspicious     → actor -0.20

设计:
- 策略可注册多个 handler（不同事件不同规则）
- 调整后通过 AgentRegistry.update_trust 写回
- 不直接修改 trust_score，而是通过 manager 维持 audit trail
"""
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ..infra.events import Event, EventBus
from .registry import AgentRegistry

logger = logging.getLogger(__name__)


# 默认事件策略: event_type -> [(actor_field, delta), ...]
DEFAULT_POLICIES: dict[str, list[tuple[str, float]]] = {
    "delegation.placed": [
        ("from_agent_id", +0.10),
        ("to_agent_id", +0.20),
    ],
    "delegation.accepted": [
        ("to_agent_id", +0.05),
    ],
    "delegation.cancelled": [
        ("actor", -0.05),  # 谁取消谁扣
    ],
    "task.completed": [
        ("owner_agent_id", +0.02),
    ],
    "task.failed": [
        ("owner_agent_id", -0.05),
    ],
    "security.suspicious": [
        ("actor", -0.20),
    ],
}


class TrustStrategy:
    """信任分调整策略"""

    def __init__(self, registry: AgentRegistry, event_bus: EventBus | None = None,
                 policies: dict[str, list[tuple[str, float]]] | None = None) -> None:
        self._reg = registry
        self._bus = event_bus
        self._policies = policies or DEFAULT_POLICIES
        self._history: list[dict] = []   # 调整记录
        self._subscribed = False
        if event_bus is not None:
            self.attach(event_bus)

    def attach(self, event_bus: EventBus) -> None:
        """订阅 event_bus"""
        if self._subscribed:
            return
        event_bus.subscribe("*", self._on_event)
        self._bus = event_bus
        self._subscribed = True
        logger.info("TrustStrategy 已订阅 EventBus")

    def detach(self) -> None:
        if self._bus is not None and self._subscribed:
            self._bus.unsubscribe("*", self._on_event)
            self._subscribed = False

    def _on_event(self, event: Event) -> None:
        """EventBus 回调: 根据 event.type 应用策略"""
        if event.type not in self._policies:
            return
        for field_name, delta in self._policies[event.type]:
            agent_id = self._extract_agent_id(event.payload, field_name)
            if agent_id:
                self._apply(agent_id, delta, event)

    def _extract_agent_id(self, payload: dict, field_name: str) -> str | None:
        """从 event payload 提取 agent_id
        支持的字段名:
        - owner_agent_id / from_agent_id / to_agent_id / actor / actor_agent_id
        """
        # 直接取
        for k in (field_name, "actor", "actor_agent_id", "owner_agent_id",
                  "from_agent_id", "to_agent_id"):
            if k in payload and payload[k]:
                return payload[k]
        return None

    def _apply(self, agent_id: str, delta: float, event: Event) -> float | None:
        """应用信任分调整"""
        new_score = self._reg.update_trust(agent_id, delta)
        record = {
            "agent_id": agent_id,
            "event_type": event.type,
            "delta": delta,
            "new_score": new_score,
            "timestamp": event.timestamp,
        }
        self._history.append(record)
        if new_score is None:
            logger.debug(f"TrustStrategy: agent '{agent_id}' 不存在, 跳过")
        else:
            logger.info(f"TrustStrategy: {agent_id} {delta:+.2f} → {new_score:.2f} (by {event.type})")
        return new_score

    # ---------- 手动 ----------
    def apply_manual(self, agent_id: str, delta: float, reason: str = "manual") -> float | None:
        """手动调整（不走事件）"""
        new_score = self._reg.update_trust(agent_id, delta)
        self._history.append({
            "agent_id": agent_id, "event_type": "manual",
            "delta": delta, "new_score": new_score,
            "reason": reason, "timestamp": datetime.now(UTC).isoformat(),
        })
        return new_score

    # ---------- 查询 ----------
    def history(self, agent_id: str | None = None, limit: int = 50) -> list[dict]:
        if agent_id is None:
            return self._history[-limit:]
        return [h for h in self._history if h.get("agent_id") == agent_id][-limit:]

    def policy_for(self, event_type: str) -> list[tuple[str, float]]:
        return list(self._policies.get(event_type, []))

    def add_policy(self, event_type: str, actor_field: str, delta: float) -> None:
        self._policies.setdefault(event_type, []).append((actor_field, delta))
