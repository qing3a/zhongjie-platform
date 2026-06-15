"""
L3 Governance - TrustAwareEngine
对应 P5 M24: 信任驱动的动态审批

设计:
- 包装 RuleEngine
- 在规则引擎前做"信任预评估":
  - trust_score >= HIGH_TRUST → 直接 auto_approve (跳过规则)
  - trust_score <= LOW_TRUST → 直接 manual_review (强制审批)
  - 其他 → 走正常 RuleEngine
- 决策过程记录在 audit log
"""
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .engine import RuleEngine
from .models import ActionType, Request, RequestStatus

logger = logging.getLogger(__name__)


@dataclass
class GovernanceDecision:
    """治理决策记录"""
    request_id: str
    owner_agent_id: str | None
    trust_score: float | None
    decision: str               # "auto_approved_via_trust" / "manual_review_via_trust" / "rule_match" / "default_manual"
    matched_rule: str | None
    trust_skip_applied: bool
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    note: str = ""


class TrustAwareEngine:
    """信任感知的规则引擎"""

    HIGH_TRUST_THRESHOLD = 0.85
    LOW_TRUST_THRESHOLD = 0.30

    def __init__(self, rule_engine: RuleEngine | None = None,
                 high_trust: float = HIGH_TRUST_THRESHOLD,
                 low_trust: float = LOW_TRUST_THRESHOLD) -> None:
        self._engine = rule_engine or RuleEngine()
        self._high = high_trust
        self._low = low_trust
        self._decisions: list[GovernanceDecision] = []

    @property
    def rule_engine(self) -> RuleEngine:
        return self._engine

    def set_thresholds(self, high: float, low: float) -> None:
        self._high = high
        self._low = low

    def process(self, request: Request, owner_agent_id: str | None = None,
                trust_score: float | None = None) -> dict:
        """处理请求
        流程:
        1. 信任预评估 (如果 trust_score 给出)
        2. 走 RuleEngine
        3. 记录决策
        """
        decision = self._make_decision(request, owner_agent_id, trust_score)
        self._decisions.append(decision)

        # 信任预评估生效
        if decision.trust_skip_applied and decision.decision == "auto_approved_via_trust":
            request.status = RequestStatus.APPROVED
            return {
                "request_id": request.id,
                "matched_rule": None,
                "matched_rule_name": "信任豁免",
                "action": ActionType.AUTO_APPROVE.value,
                "status": request.status.value,
                "trust_score": trust_score,
            }
        if decision.trust_skip_applied and decision.decision == "manual_review_via_trust":
            # 直接走 manual_review，跳过规则（也跳过 AUTO_APPROVE）
            request.status = RequestStatus.PENDING
            self._engine.approval_desk.enqueue(request)
            return {
                "request_id": request.id,
                "matched_rule": None,
                "matched_rule_name": "低信任强制审批",
                "action": ActionType.MANUAL_REVIEW.value,
                "status": request.status.value,
                "trust_score": trust_score,
            }

        # 走 RuleEngine
        return self._engine.process(request)

    def _make_decision(self, request: Request, owner_agent_id: str | None,
                       trust_score: float | None) -> GovernanceDecision:
        if trust_score is None:
            return GovernanceDecision(
                request_id=request.id, owner_agent_id=owner_agent_id,
                trust_score=None, decision="default_manual",
                matched_rule=None, trust_skip_applied=False,
                note="未提供 trust_score, 走规则引擎",
            )
        if trust_score >= self._high:
            return GovernanceDecision(
                request_id=request.id, owner_agent_id=owner_agent_id,
                trust_score=trust_score, decision="auto_approved_via_trust",
                matched_rule=None, trust_skip_applied=True,
                note=f"高信任 {trust_score:.2f} >= {self._high}, 跳过审批",
            )
        if trust_score <= self._low:
            return GovernanceDecision(
                request_id=request.id, owner_agent_id=owner_agent_id,
                trust_score=trust_score, decision="manual_review_via_trust",
                matched_rule=None, trust_skip_applied=True,
                note=f"低信任 {trust_score:.2f} <= {self._low}, 强制审批",
            )
        return GovernanceDecision(
            request_id=request.id, owner_agent_id=owner_agent_id,
            trust_score=trust_score, decision="rule_match",
            matched_rule=None, trust_skip_applied=False,
            note=f"中等信任 {trust_score:.2f}, 走规则引擎",
        )

    # ---------- 决策历史 ----------
    def history(self, agent_id: str | None = None, limit: int = 50) -> list[GovernanceDecision]:
        if agent_id is None:
            return self._decisions[-limit:]
        return [d for d in self._decisions if d.owner_agent_id == agent_id][-limit:]

    def stats(self) -> dict:
        total = len(self._decisions)
        if total == 0:
            return {"total": 0, "by_decision": {}}
        by_decision: dict[str, int] = {}
        for d in self._decisions:
            by_decision[d.decision] = by_decision.get(d.decision, 0) + 1
        return {
            "total": total,
            "by_decision": by_decision,
            "trust_skip_rate": round(
                (by_decision.get("auto_approved_via_trust", 0)
                 + by_decision.get("manual_review_via_trust", 0)) / total, 3),
        }
