"""
L1 Infrastructure - 持久化后端抽象
- JsonBackend: 复用 atomic write (与 p1_p2.py:2488 PersistenceManager 行为一致)
- SqliteBackend: 复用 p1_p2.py SQLite 切换 (后续完整搬)
- Storage: 顶层 facade，根据 SQLITE_ENABLED 切换
"""
import json
import logging
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class StorageBackend(Protocol):
    """存储后端接口 - 后续所有 Manager 共享"""
    def save(self, name: str, data: Any) -> None: ...
    def load(self, name: str, default: Any = None) -> Any: ...


class JsonBackend:
    """JSON 文件后端，原子写（与老实现一致）"""
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, data: Any) -> None:
        path = self.data_dir / name
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)

    def load(self, name: str, default: Any = None) -> Any:
        path = self.data_dir / name
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"加载 {name} 失败: {e}")
            return default


class SqliteBackend:
    """SQLite 后端 - 简化版
    完整搬 p1_p2.py 的 sqlite_option 留到 M5
    """
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = __import__("threading").Lock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """最小表结构，与 p1_p2.py migrate_to_sqlite.py 兼容"""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kv_store (
                    name TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            self._conn.commit()

    def save(self, name: str, data: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv_store (name, data, updated_at) VALUES (?, ?, ?)",
                (name, json.dumps(data, ensure_ascii=False), datetime.now(UTC).isoformat()),
            )
            self._conn.commit()

    def load(self, name: str, default: Any = None) -> Any:
        with self._lock:
            cur = self._conn.execute("SELECT data FROM kv_store WHERE name = ?", (name,))
            row = cur.fetchone()
        if not row:
            return default
        try:
            return json.loads(row[0])
        except Exception:
            return default

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class Storage:
    """存储 facade - 根据配置选择后端
    行为与老 p1_p2.py PersistenceManager + sqlite_option 切换一致
    """
    def __init__(self, data_dir: str | Path = "data", sqlite_enabled: bool = False, sqlite_path: str | Path = "data/mediator.db") -> None:
        self.data_dir = Path(data_dir)
        if sqlite_enabled:
            self._backend: StorageBackend = SqliteBackend(Path(sqlite_path))
        else:
            self._backend = JsonBackend(self.data_dir)

    @property
    def backend(self) -> StorageBackend:
        return self._backend

    def save(self, name: str, data: Any) -> None:
        self._backend.save(name, data)

    def load(self, name: str, default: Any = None) -> Any:
        return self._backend.load(name, default)

    def close(self) -> None:
        if isinstance(self._backend, SqliteBackend):
            self._backend.close()
