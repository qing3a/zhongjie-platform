"""
L7 AI - 内容审核 (classify)

评估文本的风险等级 + 类别标签, 用于:
- JD 发布的实时审核
- 简历/帖子垃圾识别
- 站外交易诱导识别
- 涉黄/涉政/涉暴识别

设计:
- 输入: 待审核文本 (jd_text / post_text / candidate_claim)
- 输出: ClassifyResult {risk_score 0-1, categories: set, action: allow|review|block, reason}
- 风险分级:
  - < 0.3 → allow (放行)
  - 0.3-0.7 → review (人工二审, 进队列)
  - > 0.7 → block (拒绝, 通知用户)
- 类别: SPAM / FRAUD / OFFTOPIC / ILLEGAL / SEXUAL / NORMAL
- Stub 模式: 关键词命中 (按类目查表) + 简单权重
- LLM 模式: prompt 让模型给 0-1 分 + 类别标签

非目标 (v0.3):
- 不做图像审核 (那是 ai/image_audit.py v0.3.1+)
- 不做实人认证 (那是 risk/identity_check.py)
- 不做细粒度法律合规 (留给法务)
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .llm import LLMError, LLMProvider, get_provider
from .models import ClassifyRequest, ClassifyResult
from .prompts import CLASSIFY_SYSTEM, CLASSIFY_USER_TEMPLATE

logger = logging.getLogger(__name__)


# ==================== 风险类别常量 ====================

class RiskCategory:
    NORMAL = "NORMAL"
    SPAM = "SPAM"           # 垃圾广告
    FRAUD = "FRAUD"         # 欺诈 (虚假承诺 / 收钱跑路)
    OFFTOPIC = "OFFTOPIC"   # 跑题 (招聘 app 发广告)
    ILLEGAL = "ILLEGAL"     # 违法 (涉黄/涉政/涉暴/毒品)
    SEXUAL = "SEXUAL"       # 涉黄 (软色情, 招聘里也是高风险)

    ALL = {NORMAL, SPAM, FRAUD, OFFTOPIC, ILLEGAL, SEXUAL}


class RiskAction:
    ALLOW = "allow"      # 风险 < 0.3
    REVIEW = "review"    # 0.3 <= 风险 < 0.7
    BLOCK = "block"      # 风险 >= 0.7


# ==================== Stub 模式: 风险关键词库 ====================

# 每个类别: 关键词 + 命中权重 (0-1)
RISK_KEYWORDS: dict[str, list[tuple[str, float]]] = {
    RiskCategory.SPAM: [
        ("加微信", 0.4), ("加 wx", 0.4), ("加 vx", 0.4), ("私信", 0.2),
        ("免费送", 0.5), ("点击链接", 0.6), ("扫码", 0.3), ("代理", 0.2),
        ("兼职", 0.2), ("日结", 0.4), ("日赚", 0.5), ("千元", 0.2),
        ("躺赚", 0.6), ("0 门槛", 0.4), ("无经验", 0.2),
        ("广告", 0.3), ("推广", 0.2), ("代发", 0.4),
    ],
    RiskCategory.FRAUD: [
        ("高薪", 0.3), ("高收入", 0.4), ("轻松", 0.2), ("无学历", 0.3),
        ("保证", 0.2), ("包过", 0.4), ("百分百", 0.4), ("100%", 0.3),
        ("先交钱", 0.6), ("押金", 0.5), ("培训费", 0.4), ("入职费", 0.5),
        ("刷单", 0.8), ("刷信誉", 0.8), ("充值返现", 0.8), ("充值", 0.3),
        ("套现", 0.7), ("贷款", 0.3), ("信用卡", 0.2),
        ("内部渠道", 0.5), ("特殊关系", 0.4), ("走关系", 0.5),
        ("面试费", 0.6), ("材料费", 0.4), ("保证金", 0.5),
        ("兼职日结", 0.5), ("日赚千元", 0.7), ("押金", 0.5),
    ],
    RiskCategory.OFFTOPIC: [
        ("出售", 0.3), ("卖", 0.1), ("二手", 0.2), ("转让", 0.3),
        ("拼车", 0.5), ("搭讪", 0.6), ("交友", 0.4), ("约", 0.3),
        ("陪玩", 0.5), ("代练", 0.4), ("游戏代打", 0.5),
        ("招聘", 0.0),  # 上下文相关, 不直接算跑题
    ],
    RiskCategory.ILLEGAL: [
        ("毒品", 0.9), ("冰毒", 0.9), ("摇头丸", 0.9), ("大麻", 0.7),
        ("枪支", 0.9), ("弹药", 0.8), ("军火", 0.9),
        ("洗钱", 0.9), ("伪造", 0.6), ("假证", 0.7),
        ("办证", 0.7), ("代考", 0.7), ("替考", 0.7),
    ],
    RiskCategory.SEXUAL: [
        ("约炮", 0.9), ("一夜情", 0.9), ("色情", 0.9), ("裸聊", 0.9),
        ("陪睡", 0.9), ("上门服务", 0.5),  # 单独中性, 招聘里是 high risk
        ("潜规则", 0.6),
        ("援交", 0.9), ("性交易", 0.9),
    ],
}

# 高频但低风险的"假阳性"关键词 — 命中时降低整体分数
SOFTENING_KEYWORDS = [
    ("正规", -0.2), ("公司", -0.1), ("签合同", -0.2), ("五险一金", -0.3),
    ("面试", -0.1), ("简历", -0.1), ("招聘", -0.1), ("应聘", -0.1),
    ("工作经验", -0.1), ("学历", -0.1), ("薪资", -0.1), ("职位", -0.1),
]


def _classify_stub(text: str,
                  category_extractors: dict[str, Callable[[str], float]] | None = None) -> ClassifyResult:
    """Stub 模式: 关键词命中 + 权重累加
    风险分 = 最高单类别分 × 0.7 + 次高 × 0.3 (考虑多类别叠加)
    """
    text_lower = text.lower()

    # 每个类别算分
    cat_scores: dict[str, float] = {}
    for cat in RiskCategory.ALL:
        if cat == RiskCategory.NORMAL:
            continue
        score = 0.0
        for kw, weight in RISK_KEYWORDS.get(cat, []):
            if kw.lower() in text_lower:
                score = max(score, weight)  # 类内取最高
        cat_scores[cat] = score

    # 加 softening
    for kw, delta in SOFTENING_KEYWORDS:
        if kw in text:
            for c in cat_scores:
                cat_scores[c] = max(0.0, cat_scores[c] + delta)

    # 排序, top 2
    sorted_cats = sorted(cat_scores.items(), key=lambda x: x[1], reverse=True)
    top2 = [c for c, s in sorted_cats[:2] if s > 0.0]
    primary_cat = top2[0] if top2 else RiskCategory.NORMAL

    # 风险总分:
    # - 单类别 ≥ 0.8 (FRAUD/ILLEGAL/SEXUAL 高危) → 直接 0.85+ (强制 block)
    # - 否则: 最高类目 0.7 + 次高 0.3
    # - 无命中 → 默认 0.05
    if not top2:
        risk_score = 0.05
    elif sorted_cats[0][1] >= 0.8 and sorted_cats[0][0] in {
        RiskCategory.FRAUD, RiskCategory.ILLEGAL, RiskCategory.SEXUAL
    }:
        # 高危类别: 单命中即 block
        risk_score = max(0.85, sorted_cats[0][1])
    else:
        risk_score = sorted_cats[0][1] * 0.7
        if len(sorted_cats) > 1 and sorted_cats[1][1] > 0:
            risk_score += sorted_cats[1][1] * 0.3
    risk_score = min(1.0, max(0.0, risk_score))

    # Action
    if risk_score < 0.3:
        action = RiskAction.ALLOW
    elif risk_score < 0.7:
        action = RiskAction.REVIEW
    else:
        action = RiskAction.BLOCK

    # Reason
    if not top2:
        reason = "无风险关键词命中"
    else:
        reason = f"命中 {primary_cat} 类别 (分数 {risk_score:.2f})"

    return ClassifyResult(
        request_id=str(uuid.uuid4()),
        text_preview=text[:100],
        risk_score=round(risk_score, 3),
        primary_category=primary_cat,
        categories=top2,
        action=action,
        reason=reason,
        provider="stub",
        model="stub-v1",
        source="stub",
    )


# ==================== LLM 模式 ====================

def classify_text(req: ClassifyRequest, *,
                  provider: LLMProvider | None = None) -> ClassifyResult:
    """审核一段文本
    LLM 模式: prompt 让模型给 0-1 分 + 类别
    Stub 模式: 关键词命中
    """
    provider = provider or get_provider()
    text = req.text
    mode = req.mode

    if mode == "stub" or (mode == "auto" and provider.name == "stub"):
        return _classify_stub(text)

    if mode in ("llm", "auto"):
        try:
            system = CLASSIFY_SYSTEM
            user = CLASSIFY_USER_TEMPLATE.format(
                text=text,
                context=req.context or "通用",
            )
            raw = provider.complete(
                system, user,
                temperature=0.0,  # 审核任务用 0 温度
                max_tokens=500,
            )
            parsed = _parse_llm_json(raw)
            return ClassifyResult(
                request_id=str(uuid.uuid4()),
                text_preview=text[:100],
                risk_score=float(parsed.get("risk_score", 0.5)),
                primary_category=parsed.get("primary_category", RiskCategory.NORMAL),
                categories=parsed.get("categories", []),
                action=parsed.get("action", RiskAction.REVIEW),
                reason=parsed.get("reason", ""),
                provider=provider.name,
                model=getattr(provider, "_default_model", None) or f"{provider.name}-v1",
                source="llm",
            )
        except (LLMError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"classify_text LLM call failed: {e}, fallback to stub")
            return _classify_stub(text)

    raise ValueError(f"Unknown mode: {mode!r}")


def _parse_llm_json(raw: str) -> dict:
    """与 extract.py 同款解析 (容忍 markdown fence)"""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n", 1)
        if len(lines) > 1:
            raw = lines[1]
        if raw.endswith("```"):
            raw = raw[:-3]
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    return json.loads(raw)


__all__ = [
    "classify_text",
    "RiskCategory",
    "RiskAction",
    "RISK_KEYWORDS",
    "SOFTENING_KEYWORDS",
]
