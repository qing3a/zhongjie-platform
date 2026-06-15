"""
L1 Infrastructure - 配置管理
对应老 p1_p2.py:2379-2457 ConfigManager
支持嵌套 key 路径 (rate_limit.default)、mtime 检测热加载
"""
from pathlib import Path
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理
    对应老 p1_p2.py:2379-2457 ConfigManager
    行为兼容：嵌套 key 路径、mtime 检测热加载
    """

    def __init__(self, config_path: Path | str = "data/config.json") -> None:
        self.config_path = Path(config_path)
        self._data: dict = {}
        self._mtime: float = 0.0
        self.reload()

    def reload(self) -> None:
        """检测 mtime 变更，触发热加载"""
        if not self.config_path.exists():
            self._data = {}
            self._mtime = 0.0
            return
        mtime = self.config_path.stat().st_mtime
        if mtime != self._mtime:
            try:
                self._data = json.loads(self.config_path.read_text(encoding="utf-8"))
                self._mtime = mtime
                logger.info(f"配置已加载: {self.config_path}")
            except Exception as e:
                logger.warning(f"配置加载失败: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        self.reload()  # 热加载检测
        return self._get_nested(self._data, key, default)

    def set(self, key: str, value: Any) -> None:
        self.reload()
        self._set_nested(self._data, key, value)
        self._save()

    def _get_nested(self, data: dict, key: str, default: Any) -> Any:
        parts = key.split(".")
        cur = data
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return default
        return cur

    def _set_nested(self, data: dict, key: str, value: Any) -> None:
        parts = key.split(".")
        cur = data
        for p in parts[:-1]:
            if p not in cur or not isinstance(cur[p], dict):
                cur[p] = {}
            cur = cur[p]
        cur[parts[-1]] = value

    def _save(self) -> None:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.config_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.config_path)
            self._mtime = self.config_path.stat().st_mtime
        except Exception as e:
            logger.warning(f"配置保存失败: {e}")
