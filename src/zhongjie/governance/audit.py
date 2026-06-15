"""
L3 Governance - 治理决策审计
对应 P5 M25: 不可篡改的决策日志 + 复盘查询

特性:
- append-only: 不允许修改/删除已记录
- 链式 hash: 每条记录 hash 包含前一条 hash（防篡改）
- 复盘查询: 按 agent / time / decision_type / trust_score 范围
"""
import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class AuditEntry:
    """一条审计记录（不可变）"""
    id: str                          # aud_xxxxx
    request_id: str
    owner_agent_id: str | None
    decision: str                    # auto_approved_via_trust / manual_review_via_trust / rule_match / ...
    matched_rule: str | None
    trust_score: float | None
    timestamp: str
    prev_hash: str = ""              # 前一条 hash（防篡改）
    hash: str = ""                   # 本条 hash = sha256(prev_hash + 内容)
    note: str = ""
    payload_snapshot: dict = field(default_factory=dict)  # 请求时 payload 快照


class AppendOnlyAuditLog:
    """append-only 审计日志
    链式 hash: 每条 hash = sha256(prev_hash + 本条 JSON)
    如要修改历史，需重算所有 hash；外部可校验一致性
    """

    def __init__(self, data_dir: str | Path = "data", filename: str = "governance_audit.json") -> None:
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / filename
        self._entries: list[AuditEntry] = []
        self._lock = threading.Lock()
        self._load()

    def append(self, entry: AuditEntry) -> AuditEntry:
        """追加一条记录，自动计算 hash"""
        with self._lock:
            prev_hash = self._entries[-1].hash if self._entries else ""
            entry.prev_hash = prev_hash
            entry.hash = self._compute_hash(entry)
            self._entries.append(entry)
            self._persist()
        return entry

    def _compute_hash(self, entry: AuditEntry) -> str:
        content = json.dumps({
            "id": entry.id, "request_id": entry.request_id,
            "owner_agent_id": entry.owner_agent_id, "decision": entry.decision,
            "matched_rule": entry.matched_rule, "trust_score": entry.trust_score,
            "timestamp": entry.timestamp, "note": entry.note,
            "prev_hash": entry.prev_hash,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    # ---------- 查询 ----------
    def all(self) -> list[AuditEntry]:
        with self._lock:
            return list(self._entries)

    def by_agent(self, agent_id: str) -> list[AuditEntry]:
        with self._lock:
            return [e for e in self._entries if e.owner_agent_id == agent_id]

    def by_decision(self, decision: str) -> list[AuditEntry]:
        with self._lock:
            return [e for e in self._entries if e.decision == decision]

    def by_trust_range(self, low: float | None = None, high: float | None = None) -> list[AuditEntry]:
        with self._lock:
            out = []
            for e in self._entries:
                if e.trust_score is None:
                    continue
                if low is not None and e.trust_score < low:
                    continue
                if high is not None and e.trust_score > high:
                    continue
                out.append(e)
            return out

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def verify_integrity(self) -> tuple[bool, list[str]]:
        """校验链式 hash 完整性
        返回 (is_valid, list_of_issues)
        """
        issues: list[str] = []
        with self._lock:
            for i, e in enumerate(self._entries):
                expected_prev = self._entries[i-1].hash if i > 0 else ""
                if e.prev_hash != expected_prev:
                    issues.append(f"Entry {e.id}: prev_hash mismatch (expected {expected_prev[:8]}, got {e.prev_hash[:8]})")
                # 验证 hash
                recomputed = self._compute_hash(e)
                if recomputed != e.hash:
                    issues.append(f"Entry {e.id}: hash mismatch (content tampered)")
        return (len(issues) == 0, issues)

    # ---------- 统计 ----------
    def stats(self) -> dict:
        with self._lock:
            if not self._entries:
                return {"total": 0, "by_decision": {}}
            by_decision: dict[str, int] = {}
            for e in self._entries:
                by_decision[e.decision] = by_decision.get(e.decision, 0) + 1
            trust_scores = [e.trust_score for e in self._entries if e.trust_score is not None]
            return {
                "total": len(self._entries),
                "by_decision": by_decision,
                "trust_score": {
                    "min": min(trust_scores) if trust_scores else None,
                    "max": max(trust_scores) if trust_scores else None,
                    "avg": round(sum(trust_scores) / len(trust_scores), 3) if trust_scores else None,
                },
            }

    # ---------- 持久化 ----------
    def _persist(self) -> None:
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            data = [asdict(e) for e in self._entries]
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except Exception as e:
            logger.warning(f"audit log 持久化失败: {e}")

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            with self._lock:
                for item in raw:
                    if isinstance(item, dict) and "id" in item:
                        e = AuditEntry(**item)
                        self._entries.append(e)
            logger.info(f"[AuditLog] 加载 {len(self._entries)} 条审计")
        except Exception as e:
            logger.warning(f"audit log 加载失败: {e}")
