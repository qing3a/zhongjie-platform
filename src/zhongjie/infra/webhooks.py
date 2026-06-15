"""
L1 Infrastructure - Webhook 管理
对应老 p1_p2.py:1494-1597 WebhookManager
接口级抽象：注册/取消/触发，行为兼容
完整 HTTP 投递实现留到 M5 集成阶段
"""
from collections.abc import Callable
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
import logging
import uuid

logger = logging.getLogger(__name__)


@dataclass
class WebhookRegistration:
    id: str
    url: str
    events: list[str]                            # 订阅的事件类型列表
    secret: str = ""
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class WebhookManager:
    """Webhook 管理
    对应老 p1_p2.py:1494-1597 WebhookManager
    M4 阶段：内存存储 + 事件总线集成
    M5 阶段：HTTP 投递 + 持久化
    """

    def __init__(self, event_bus=None, persist_storage=None) -> None:
        self._webhooks: dict[str, WebhookRegistration] = {}
        self._lock = Lock()
        self._event_bus = event_bus
        self._persist = persist_storage
        # 自动从 event_bus 订阅（如果提供）
        if self._event_bus is not None:
            self._event_bus.subscribe("*", self._on_event)

    def register(self, url: str, events: list[str], secret: str = "") -> WebhookRegistration:
        with self._lock:
            reg = WebhookRegistration(
                id=f"wh_{uuid.uuid4().hex[:8]}",
                url=url,
                events=events,
                secret=secret,
            )
            self._webhooks[reg.id] = reg
            self._persist_webhooks()
            return reg

    def unregister(self, webhook_id: str) -> bool:
        with self._lock:
            if webhook_id in self._webhooks:
                del self._webhooks[webhook_id]
                self._persist_webhooks()
                return True
            return False

    def list(self, event: str | None = None) -> list[WebhookRegistration]:
        with self._lock:
            if event is None:
                return list(self._webhooks.values())
            return [w for w in self._webhooks.values() if event in w.events or "*" in w.events]

    def _on_event(self, event) -> None:
        """事件总线回调: 找出订阅此事件的 webhook，触发投递
        M4 阶段仅记录日志 + 累计统计；M5 阶段接入 HTTP 投递
        """
        matched = self.list(event.type)
        if matched:
            logger.info(f"[Webhook] 事件 {event.type} 匹配 {len(matched)} 个 webhook（投递待 M5）")
            for w in matched:
                logger.debug(f"  → {w.url} (events={w.events})")

    def _persist_webhooks(self) -> None:
        if self._persist is None:
            return
        try:
            data = [asdict(w) for w in self._webhooks.values()]
            self._persist.save("webhooks.json", data)
        except Exception as e:
            logger.warning(f"webhooks 持久化失败: {e}")
