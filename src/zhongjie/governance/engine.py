"""
规则引擎 + 审批台 - 从 p0_core.py:125-180 抽出
按优先级遍历规则，命中即终止；manual_review 进待审批队列
"""
from threading import Lock
from typing import Any

from .approval import ApprovalDesk
from .models import ActionType, Request, RequestStatus
from .rules import Rule


class RuleEngine:
    """规则引擎
    对应老 p0_core.py:125-180
    增加线程安全（Lock 保护 manual_review_queue）
    """

    def __init__(self, approval_desk: ApprovalDesk | None = None) -> None:
        self.rules: list[Rule] = []
        self._lock = Lock()
        self.approval_desk = approval_desk or ApprovalDesk()

    def add_rule(self, rule: Rule) -> None:
        with self._lock:
            self.rules.append(rule)
            # 按优先级排序，高优先级在前
            self.rules.sort(key=lambda r: -r.priority)

    def remove_rule(self, rule_id: str) -> bool:
        with self._lock:
            before = len(self.rules)
            self.rules = [r for r in self.rules if r.id != rule_id]
            return len(self.rules) < before

    def get_rule(self, rule_id: str) -> Rule | None:
        for r in self.rules:
            if r.id == rule_id:
                return r
        return None

    def process(self, request: Request) -> dict:
        """处理请求，返回处理结果
        - 命中规则 → 应用 action
        - 未命中 → 默认 manual_review
        """
        with self._lock:
            for rule in self.rules:
                if rule.match(request):
                    if rule.action == ActionType.MANUAL_REVIEW:
                        request.status = RequestStatus.PENDING
                        self.approval_desk.enqueue(request)
                    elif rule.action == ActionType.AUTO_APPROVE:
                        request.status = RequestStatus.APPROVED
                    elif rule.action == ActionType.AUTO_REJECT:
                        request.status = RequestStatus.REJECTED
                    elif rule.action == ActionType.ROUTE_DIRECTLY:
                        request.status = RequestStatus.ROUTING
                    return {
                        "request_id": request.id,
                        "matched_rule": rule.id,
                        "matched_rule_name": rule.name,
                        "action": rule.action.value,
                        "status": request.status.value,
                    }
            # 未命中 → 默认 manual_review
            request.status = RequestStatus.PENDING
            self.approval_desk.enqueue(request)
            return {
                "request_id": request.id,
                "matched_rule": None,
                "matched_rule_name": "默认规则",
                "action": ActionType.MANUAL_REVIEW.value,
                "status": request.status.value,
            }

    # ------- 审批便捷方法（委托给 ApprovalDesk） -------
    def approve(self, request_id: str, decided_by: str = "admin", comment: str = "") -> bool:
        return self.approval_desk.approve(request_id, decided_by, comment)

    def reject(self, request_id: str, decided_by: str = "admin", comment: str = "") -> bool:
        return self.approval_desk.reject(request_id, decided_by, comment)

    def list_pending(self) -> list[Request]:
        return self.approval_desk.list_pending()
