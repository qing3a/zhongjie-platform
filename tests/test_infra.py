"""
M4 单元测试 - 验证基础设施层
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zhongjie.infra.config import ConfigManager
from zhongjie.infra.events import Event, EventBus
from zhongjie.infra.persistence import JsonBackend, SqliteBackend, Storage
from zhongjie.infra.webhooks import WebhookManager


def test_json_backend_round_trip(tmp_path: Path):
    """JsonBackend: save/load 一致"""
    backend = JsonBackend(tmp_path)
    backend.save("test.json", [{"a": 1}, {"b": 2}])
    assert backend.load("test.json") == [{"a": 1}, {"b": 2}]
    # 默认值
    assert backend.load("not_exists.json", default=[]) == []


def test_sqlite_backend_round_trip(tmp_path: Path):
    """SqliteBackend: save/load 一致"""
    db = tmp_path / "test.db"
    backend = SqliteBackend(db)
    backend.save("k1", {"x": 1, "y": [1, 2, 3]})
    assert backend.load("k1") == {"x": 1, "y": [1, 2, 3]}
    assert backend.load("not_exists", default=None) is None
    backend.close()


def test_storage_facade_switches_backend(tmp_path: Path):
    """Storage: 根据 sqlite_enabled 切换后端"""
    s_json = Storage(data_dir=tmp_path, sqlite_enabled=False)
    s_json.save("a.json", [1, 2, 3])
    assert s_json.load("a.json") == [1, 2, 3]

    db = tmp_path / "s.db"
    s_sql = Storage(data_dir=tmp_path, sqlite_enabled=True, sqlite_path=db)
    s_sql.save("b", "hello")
    assert s_sql.load("b") == "hello"
    s_sql.close()


def test_config_nested_key(tmp_path: Path):
    """ConfigManager: 嵌套 key 路径"""
    cfg_path = tmp_path / "config.json"
    cfg = ConfigManager(cfg_path)
    cfg.set("rate_limit.default", 100)
    cfg.set("rate_limit.window", 60)
    cfg.set("feature.flag_a", True)
    assert cfg.get("rate_limit.default") == 100
    assert cfg.get("rate_limit.window") == 60
    assert cfg.get("feature.flag_a") is True
    assert cfg.get("missing.key", "fallback") == "fallback"


def test_config_persists_across_instances(tmp_path: Path):
    """ConfigManager: 持久化后重新加载能取到值"""
    cfg_path = tmp_path / "config.json"
    cfg1 = ConfigManager(cfg_path)
    cfg1.set("test.value", "persisted")
    cfg2 = ConfigManager(cfg_path)
    assert cfg2.get("test.value") == "persisted"


def test_event_bus_basic_publish_subscribe():
    """EventBus: 订阅 + 触发"""
    bus = EventBus()
    received = []
    bus.subscribe("user.created", lambda e: received.append(e))
    n = bus.emit("user.created", {"name": "alice"})
    assert n == 1
    assert len(received) == 1
    assert received[0].payload == {"name": "alice"}


def test_event_bus_wildcard():
    """EventBus: '*' 订阅所有事件"""
    bus = EventBus()
    received = []
    bus.subscribe("*", lambda e: received.append(e))
    bus.emit("a")
    bus.emit("b")
    bus.emit("c")
    assert len(received) == 3


def test_event_bus_handler_exception_isolated():
    """EventBus: 单个 handler 抛异常不影响其他"""
    bus = EventBus()
    received = []
    def bad_handler(e): raise RuntimeError("boom")
    def good_handler(e): received.append(e)
    bus.subscribe("test", bad_handler)
    bus.subscribe("test", good_handler)
    n = bus.emit("test")
    assert n == 1   # 只有 good_handler 成功
    assert len(received) == 1


def test_event_bus_history():
    """EventBus: 历史查询"""
    bus = EventBus()
    bus.emit("a", {"i": 1})
    bus.emit("b", {"i": 2})
    bus.emit("a", {"i": 3})
    all_hist = bus.history()
    a_hist = bus.history("a")
    assert len(all_hist) == 3
    assert len(a_hist) == 2


def test_webhook_manager_register_and_list():
    """WebhookManager: 注册 + 列表"""
    wm = WebhookManager()
    reg = wm.register("https://example.com/hook", events=["order.created"])
    assert reg.id.startswith("wh_")
    assert reg.url == "https://example.com/hook"
    listed = wm.list()
    assert len(listed) == 1


def test_webhook_manager_unregister():
    """WebhookManager: 取消注册"""
    wm = WebhookManager()
    reg = wm.register("https://x.com", events=["*"])
    assert wm.unregister(reg.id)
    assert wm.unregister(reg.id) is False  # 二次失败
    assert wm.list() == []


def test_webhook_listened_to_event_bus(caplog):
    """WebhookManager: 通过 EventBus 自动收到事件通知"""
    bus = EventBus()
    wm = WebhookManager(event_bus=bus)
    wm.register("https://x.com", events=["test.event"])
    # 触发事件
    bus.emit("test.event", {"x": 1})
    # 不抛异常 + 列表能找到订阅
    assert len(wm.list("test.event")) == 1
