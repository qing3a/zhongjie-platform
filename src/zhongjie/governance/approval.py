"""
审批台 - 独立的待审批队列管理
从 RuleEngine 抽出，老 p0_core.py 把队列放在 engine 上
现在拆出，让 governance 关注点分离
"""
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
from threading import Lock
from typing import Literal

from .models import Decision, Request, RequestStatus


@dataclass
class ApprovalRecord:
    """审批记录（与老 p1_p2.py Approval 一致）"""
    id: str
    request_id: str
    rule_id: str | None
    decided_by: str
    decision: Decision
    comment: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    decided_at: str | None = None


class ApprovalDesk:
    """待审批队列 + 审批决策
    老 p0_core.py:164-180 的 approve/reject 逻辑搬到这里
    增补：线程安全 + 审计记录
    """

    def __init__(self) -> None:
        self._queue: list[Request] = []
        self._records: list[ApprovalRecord] = []
        self._lock = Lock()

    def enqueue(self, request: Request) -> None:
        """把请求加入待审批队列"""
        with self._lock:
            if not any(r.id == request.id for r in self._queue):
                self._queue.append(request)

    def list_pending(self) -> list[Request]:
        with self._lock:
            return list(self._queue)

    def find(self, request_id: str) -> Request | None:
        with self._lock:
            for r in self._queue:
                if r.id == request_id:
                    return r
            return None

    def approve(self, request_id: str, decided_by: str = "admin", comment: str = "") -> bool:
        with self._lock:
            for i, req in enumerate(self._queue):
                if req.id == request_id:
                    req.status = RequestStatus.APPROVED
                    self._queue.pop(i)
                    self._records.append(ApprovalRecord(
                        id=f"apr_{len(self._records)+1:05d}",
                        request_id=request_id,
                        rule_id=None,
                        decided_by=decided_by,
                        decision=Decision.APPROVED,
                        comment=comment,
                        decided_at=datetime.now(UTC).isoformat(),
                    ))
                    return True
            return False

    def reject(self, request_id: str, decided_by: str = "admin", comment: str = "") -> bool:
        with self._lock:
            for i, req in enumerate(self._queue):
                if req.id == request_id:
                    req.status = RequestStatus.REJECTED
                    self._queue.pop(i)
                    self._records.append(ApprovalRecord(
                        id=f"apr_{len(self._records)+1:05d}",
                        request_id=request_id,
                        rule_id=None,
                        decided_by=decided_by,
                        decision=Decision.REJECTED,
                        comment=comment,
                        decided_at=datetime.now(UTC).isoformat(),
                    ))
                    return True
            return False

    def history(self) -> list[ApprovalRecord]:
        with self._lock:
            return list(self._records)
