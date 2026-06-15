"""
通用 Repository - 线程安全 + 持久化
修老代码 _jd_storage 等无锁的 bug（M2 顺手修）
"""
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Generic, TypeVar
import json
import logging

T = TypeVar("T")

logger = logging.getLogger(__name__)


class InMemoryRepository(Generic[T]):
    """通用内存 Repository，线程安全

    用法：
        repo = InMemoryRepository[JD](data_dir=Path("data"), filename="jd.json",
                                     from_dict=JD.from_dict)
        record = repo.save(jd_obj)
        jd = repo.get("jd_xxx")
    """

    def __init__(
        self,
        data_dir: Path,
        filename: str,
        from_dict: Callable[[dict], T],
        to_dict: Callable[[T], dict] | None = None,
    ) -> None:
        self._data_dir = data_dir
        self._filename = filename
        self._from_dict = from_dict
        self._to_dict = to_dict or (lambda x: x.to_dict() if hasattr(x, "to_dict") else dict(x))
        self._store: dict[str, T] = {}
        self._lock = Lock()
        self._persist_path = data_dir / filename

    # ---------- 内存操作（线程安全） ----------
    def save(self, record: T) -> T:
        """保存记录（不持久化，调用方按需 persist）"""
        key = self._key_of(record)
        with self._lock:
            self._store[key] = record
        return record

    def get(self, key: str) -> T | None:
        with self._lock:
            value = self._store.get(key)
            # 多进程场景：miss 时从磁盘 reload 一次（其他进程可能刚写入）
            if value is None and self._persist_path.exists():
                self._load_unlocked()
                value = self._store.get(key)
            return value

    def _load_unlocked(self) -> None:
        """从磁盘 reload（持锁状态下调用）"""
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for item in raw:
                if isinstance(item, dict) and "id" in item:
                    rec = self._from_dict(item)
                    self._store[rec.id] = rec
        except Exception:
            pass

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._store

    def list_all(self) -> list[T]:
        with self._lock:
            return list(self._store.values())

    def values(self) -> list[T]:
        return self.list_all()

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    # ---------- 持久化 ----------
    def persist(self) -> None:
        """原子写入 JSON: tmp + replace（与老实现一致）"""
        with self._lock:
            snapshot = [self._to_dict(r) for r in self._store.values()]
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._persist_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._persist_path)
        except Exception as e:
            logger.warning(f"{self._filename} 持久化失败: {e}")

    def load(self) -> int:
        """启动时从 JSON 加载，返回加载条数"""
        if not self._persist_path.exists():
            return 0
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
            with self._lock:
                for item in raw:
                    if isinstance(item, dict) and "id" in item:
                        rec = self._from_dict(item)
                        self._store[rec.id] = rec
            return len(self._store)
        except Exception as e:
            logger.warning(f"{self._filename} 加载失败: {e}")
            return 0

    # ---------- 内部工具 ----------
    @staticmethod
    def _key_of(record: T) -> str:
        if hasattr(record, "id"):
            return record.id
        if isinstance(record, dict) and "id" in record:
            return record["id"]
        raise ValueError("Record must have 'id' field")
