"""
L1 Infrastructure - 事件总线
【新增】 - 老 p1_p2.py 没有事件总线，是 M4 引入的新基础设施
为后续 Agent 协作（交付物二的委托场景）打基础
"""
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any
import logging
import uuid

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """领域事件"""
    type: str                                   # 如 "request.submitted" / "delegation.accepted"
    payload: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source: str | None = None                   # 哪个 agent/manager 发出
    tenant_id: str | None = None


class EventBus:
    """同步事件总线
    - 线程安全
    - 支持按 type 订阅 / 退订
    - 事件持久化到 storage（可选）
    """

    def __init__(self, persist_storage=None) -> None:
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._lock = Lock()
        self._persist_storage = persist_storage
        self._history: list[Event] = []

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """订阅事件"""
        with self._lock:
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> bool:
        with self._lock:
            if handler in self._subscribers.get(event_type, []):
                self._subscribers[event_type].remove(handler)
                return True
            return False

    def publish(self, event: Event) -> int:
        """发布事件，返回触发的 handler 数"""
        with self._lock:
            handlers = list(self._subscribers.get(event.type, []))
            # 兜底订阅者（订阅 '*' 收到所有事件）
            handlers.extend(self._subscribers.get("*", []))
            self._history.append(event)
            # 限制历史大小，避免内存泄漏
            if len(self._history) > 1000:
                self._history = self._history[-500:]

        # 触发（异常隔离，不影响其他 handler）
        triggered = 0
        for h in handlers:
            try:
                h(event)
                triggered += 1
            except Exception as e:
                logger.exception(f"事件 {event.type} handler {h.__name__} 异常: {e}")

        # 持久化（异步即可，但这里同步最简）
        if self._persist_storage is not None:
            try:
                history = [e.__dict__ for e in self._history[-200:]]
                self._persist_storage.save("events.json", history)
            except Exception as e:
                logger.warning(f"事件持久化失败: {e}")

        return triggered

    def emit(self, event_type: str, payload: dict | None = None, source: str | None = None) -> int:
        """便捷发布"""
        return self.publish(Event(type=event_type, payload=payload or {}, source=source))

    def history(self, event_type: str | None = None, limit: int = 50) -> list[Event]:
        with self._lock:
            if event_type is None:
                return list(self._history[-limit:])
            return [e for e in self._history if e.type == event_type][-limit:]
