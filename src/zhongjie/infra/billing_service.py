"""
L1 Infrastructure - BillingService
对应 P4 M21: 账单生成 + 结算

核心:
- Invoice (账单): 一笔委托产生的 N 条分润记录
- settle: 标记已结算
- list: 按 agent 维度查账单
"""
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class InvoiceLine:
    """账单中的一条分润记录"""
    agent_id: str
    amount: float
    pct: float
    role: str = "co_finder"        # owner / co_finder / platform_fee
    settled: bool = False
    settled_at: str | None = None
    currency: str = "CNY"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "InvoiceLine":
        return cls(**d)


@dataclass
class Invoice:
    """一张账单
    对应一次委托 (delegation) 的整体分润
    包含 N 条 InvoiceLine（按 fee_split 拆出）
    """
    id: str = field(default_factory=lambda: f"inv_{uuid.uuid4().hex[:8]}")
    delegation_id: str = ""
    candidate_ref: str = ""
    total_amount: float = 0.0
    currency: str = "CNY"
    lines: list[dict] = field(default_factory=list)  # list of InvoiceLine.to_dict()
    status: str = "pending"  # pending / settled / void
    created_at: str = field(default_factory=_now_iso)
    settled_at: str | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Invoice":
        return cls(**d)

    def is_settled(self) -> bool:
        return self.status == "settled" or all(l.get("settled", False) for l in self.lines)

    def line_for(self, agent_id: str) -> dict | None:
        for l in self.lines:
            if l.get("agent_id") == agent_id:
                return l
        return None


class BillingService:
    """账单服务"""

    def __init__(self, data_dir: str | Path = "data", filename: str = "invoices.json") -> None:
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / filename
        self._invoices: dict[str, Invoice] = {}
        self._lock = threading.Lock()
        self._load()

    # ---------- 创建账单 ----------
    def create_invoice(
        self, delegation_id: str, candidate_ref: str,
        total_amount: float, fee_split: list[dict] | list, currency: str = "CNY",
        note: str = "",
    ) -> Invoice:
        """按 fee_split 把总金额拆为多条 InvoiceLine
        失败抛 ValueError（fee_split 非法或 amount <= 0）
        """
        if total_amount < 0:
            raise ValueError(f"total_amount 必须 >= 0, got {total_amount}")
        # 归一化 fee_split 为 list[dict]
        if not fee_split:
            raise ValueError("fee_split 不能为空")
        norm_shares: list[dict] = []
        for s in fee_split:
            if hasattr(s, "to_dict"):
                norm_shares.append(s.to_dict())
            else:
                norm_shares.append(dict(s))
        # 计算每行金额（四舍五入到分）
        lines: list[dict] = []
        for s in norm_shares:
            pct = float(s.get("pct", 0))
            line = InvoiceLine(
                agent_id=s["agent_id"],
                amount=round(total_amount * pct, 2),
                pct=pct,
                role=s.get("role", "co_finder"),
                currency=currency,
            )
            lines.append(line.to_dict())
        inv = Invoice(
            delegation_id=delegation_id, candidate_ref=candidate_ref,
            total_amount=total_amount, currency=currency,
            lines=lines, note=note,
        )
        with self._lock:
            self._invoices[inv.id] = inv
            self._persist()
        return inv

    # ---------- 结算 ----------
    def settle(self, invoice_id: str) -> Invoice:
        """整张账单标记为已结算"""
        with self._lock:
            inv = self._invoices.get(invoice_id)
            if inv is None:
                raise ValueError(f"Invoice '{invoice_id}' 不存在")
            inv.status = "settled"
            inv.settled_at = _now_iso()
            for line in inv.lines:
                line["settled"] = True
                line["settled_at"] = inv.settled_at
            self._persist()
        return inv

    def settle_line(self, invoice_id: str, agent_id: str) -> Invoice:
        """单条分润标记为已结算（部分结算场景）"""
        with self._lock:
            inv = self._invoices.get(invoice_id)
            if inv is None:
                raise ValueError(f"Invoice '{invoice_id}' 不存在")
            for line in inv.lines:
                if line.get("agent_id") == agent_id:
                    line["settled"] = True
                    line["settled_at"] = _now_iso()
                    break
            # 检查是否全部结算
            if all(l.get("settled", False) for l in inv.lines):
                inv.status = "settled"
                inv.settled_at = _now_iso()
            self._persist()
        return inv

    # ---------- 查询 ----------
    def get(self, invoice_id: str) -> Invoice | None:
        with self._lock:
            return self._invoices.get(invoice_id)

    def list_all(self) -> list[Invoice]:
        with self._lock:
            return list(self._invoices.values())

    def list_for_agent(self, agent_id: str, settled_only: bool = False) -> list[Invoice]:
        out = []
        with self._lock:
            for inv in self._invoices.values():
                for line in inv.lines:
                    if line.get("agent_id") == agent_id:
                        if not settled_only or line.get("settled", False):
                            out.append(inv)
                            break
        return out

    def list_by_delegation(self, delegation_id: str) -> list[Invoice]:
        with self._lock:
            return [inv for inv in self._invoices.values() if inv.delegation_id == delegation_id]

    def total_paid_to(self, agent_id: str) -> float:
        """某 agent 累计已收金额"""
        total = 0.0
        for inv in self.list_for_agent(agent_id, settled_only=True):
            line = inv.line_for(agent_id)
            if line and line.get("settled"):
                total += line.get("amount", 0.0)
        return round(total, 2)

    def total_pending_to(self, agent_id: str) -> float:
        total = 0.0
        for inv in self.list_for_agent(agent_id, settled_only=False):
            line = inv.line_for(agent_id)
            if line and not line.get("settled"):
                total += line.get("amount", 0.0)
        return round(total, 2)

    # ---------- 持久化 ----------
    def count(self) -> int:
        with self._lock:
            return len(self._invoices)

    def _persist(self) -> None:
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            data = [inv.to_dict() for inv in self._invoices.values()]
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except Exception as e:
            logger.warning(f"invoices 持久化失败: {e}")

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            with self._lock:
                for item in raw:
                    if isinstance(item, dict) and "id" in item:
                        inv = Invoice.from_dict(item)
                        self._invoices[inv.id] = inv
            logger.info(f"[BillingService] 加载 {len(self._invoices)} 张账单")
        except Exception as e:
            logger.warning(f"invoices 加载失败: {e}")
