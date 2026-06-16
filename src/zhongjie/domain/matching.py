"""
L4 Domain - 匹配算法 (v0.3)

最简实现: Jaccard 技能重合 + 薪资带宽 + 工作年限
- 白盒、可解释、毫秒级
- 排序后 topK 即可
- 局限 (TODO v0.3+): 不做语义相似 / 不做 LLM 二次筛选 / 不支持开放区间
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

logger = logging.getLogger(__name__)


# ==================== 1. salary_range 解析 ====================

# 千分位逗号支持: 1,000 / 30,000-50,000
# 数字 (可选后置 K) : 30K / 30,000K / 1,000 / 1.5 / 30,000.5
# lo/hi 各自可带 K, 整体末尾的 unit 字段处理"万/元/空"等
_NUMBER_K = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*([Kk])?"
# 分隔符: - / ~ / 到 / 至 / .. / — (em dash, U+2014)
_SEPARATOR = r"([-~到至]|\.\.|—)"
# 区间: 两端都可选 K, 末尾可接 万/W/元/空
_RANGE_RE = re.compile(
    rf"{_NUMBER_K}\s*{_SEPARATOR}\s*{_NUMBER_K}\s*([Kk万Ww元]?)",
    re.UNICODE,
)
# 单值: 数字 + 可选 K/万/W
_SINGLE_RE = re.compile(rf"^\s*(\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*([Kk万Ww]?)\s*$")


@dataclass(frozen=True)
class SalaryRange:
    """薪资区间
    lo, hi: 数字原值 (带 unit)
    unit: "k" / "w" / "yuan" — 两端单位必须一致 (严格模式)
    # TODO v0.4: open_hi / open_lo 字段 (支持"30K以上" / "30K以下")
    """
    lo: float
    hi: float
    unit: str
    open_hi: bool = False
    open_lo: bool = False

    def to_kiloyuan(self) -> "SalaryRange":
        """返回一个新 SalaryRange, 数字归一到'千'"""
        return SalaryRange(
            lo=_to_kiloyuan(self.lo, self.unit),
            hi=_to_kiloyuan(self.hi, self.unit),
            unit="k",
            open_hi=self.open_hi,
            open_lo=self.open_lo,
        )

    @property
    def width(self) -> float:
        return max(0.0, self.hi - self.lo)

    @property
    def mid(self) -> float:
        return (self.lo + self.hi) / 2


def _parse_num(s: str) -> float:
    """'30,000' -> 30000.0"""
    return float(s.replace(",", ""))


def _normalize_unit(u: str) -> str:
    """统一单位表示
    k / K -> "k" (千)
    w / W / 万 -> "w" (万, 等于 10k)
    元 / 空 -> "yuan"
    """
    u = u.strip().lower()
    if u == "k":
        return "k"
    if u in ("w", "万"):
        return "w"
    return "yuan"


def _to_kiloyuan(value: float, unit: str) -> float:
    """所有数字归一到"千元" (k)
    万 = 10k, 元 = 0.001k
    """
    if unit == "k":
        return value
    if unit == "w":
        return value * 10
    return value / 1000


def _try_parse(text: str, strict: bool) -> SalaryRange | None:
    """实际 parser, 严格模式会拒绝单位混用 / 负数等。
    失败返 None, 不抛。

    返回的 SalaryRange 保留原值+原单位, 归一化在 salary_compat 内部进行.
    """
    if not text or not text.strip():
        return None
    text = text.strip()

    # 单值
    m = _SINGLE_RE.match(text)
    if m:
        try:
            v = _parse_num(m.group(1))
        except ValueError:
            return None
        if v < 0:
            return None
        u = _normalize_unit(m.group(2))
        return SalaryRange(v, v, u)

    # 区间
    m = _RANGE_RE.search(text)
    if m:
        try:
            lo = _parse_num(m.group(1))
            hi = _parse_num(m.group(4))
        except ValueError:
            return None
        if lo < 0 or hi < 0:
            return None
        # 优先级: 单值 K 标记 > 末位 unit 标记
        # 30K-50K: lo_unit="K", hi_unit="K", suffix=""  → unit = "k"
        # 30-50万: lo_unit="", hi_unit="", suffix="万" → unit = "w"
        # 30K-50: lo_unit="K", hi_unit="", suffix=""    → 混用, 严格模式拒绝
        lo_unit_raw = m.group(2) or ""
        hi_unit_raw = m.group(5) or ""
        suffix = m.group(6) or ""
        lo_unit = _normalize_unit(lo_unit_raw) if lo_unit_raw else ""
        hi_unit = _normalize_unit(hi_unit_raw) if hi_unit_raw else ""
        suffix_unit = _normalize_unit(suffix) if suffix else ""

        if lo_unit and hi_unit and lo_unit != hi_unit:
            return None  # 30K-50万 这种, 拒绝
        if lo_unit and not hi_unit and suffix_unit and suffix_unit != lo_unit:
            return None
        if hi_unit and not lo_unit and suffix_unit and suffix_unit != hi_unit:
            return None

        # 单位确定
        unit = lo_unit or hi_unit or suffix_unit or "yuan"

        if lo > hi:
            lo, hi = hi, lo
        return SalaryRange(lo, hi, unit)

    return None


def parse_range(text: str | None, *, strict: bool = True) -> SalaryRange | None:
    """解析 salary_range 字符串 → SalaryRange

    接受格式:
      "30-50K"        → (30, 50) k
      "30-50"         → (30000, 50000) yuan (30000-50000 k)
      "30K-50K"       → (30, 50) k
      "30-50万"       → (300, 500) k (万 → k 乘 10)
      "30,000-50,000" → (30000, 50000) k (千分位支持)
      "100K"          → (100, 100) k (单值视为窄区间)
      "30-30K"        → (30, 30) k (零宽)
      "30-50万"        → (300, 500) k

    不接受 (v0.3):
      "30K-50000"     → 严格模式: None (单位混用)
                       非严格: 接受, 但结果是错的, 业务层风险
      "30万-50K"      → 同上
      "30-50" (没有 K) → 严格模式: 接受, 视为 yuan (30000-50000 k)
                       这是反直觉, 但符合"无单位 = 默认元"的国内惯例
      "面议"          → None (业务层用 0.5 兼容)
      "30K以上" / "30K以下" → None (TODO v0.4)
      "abc" / "" / None → None

    严格模式默认开, 拒绝单位混用、负数。
    """
    if not text or not text.strip():
        return None
    text = text.strip()

    if strict:
        # 严格模式额外检查: 如果区间里 lo/hi 单位不一致, 拒绝
        # (regex 当前无法直接区分, 用启发式: 文本中含 K/w/万 但另一端没单位 → 拒绝)
        m = _RANGE_RE.search(text)
        if m:
            lo_text, hi_text = m.group(1), m.group(3)
            unit = m.group(4)
            # 文本里同时有 K 和不带 K 的数字 → 拒
            # 简化启发: 如果 unit 是空且数字含 "K" → 拒
            lo_has_k = "K" in lo_text or "k" in lo_text
            hi_has_k = "K" in hi_text or "k" in hi_text
            any_has_w = "万" in text or re.search(r"[Ww]\b", text) is not None
            if any_has_w and not unit:
                return None
            if unit and (lo_has_k or hi_has_k) and "万" not in text:
                # 单值 K 在区间, 但 regex unit 字段是单值 unit, 区间无法严格判
                # v0.3 简化: 单位部分只允许整体一致
                pass

    return _try_parse(text, strict)


# ==================== 2. 三个分量 ====================

def skill_overlap(jd_skills: Iterable[str], cand_skills: Iterable[str]) -> float:
    """Jaccard 相似度 ∈ [0, 1]
    空集合 → 0.0 (没有技能 = 没机会匹配)
    """
    s_jd = {s.strip().lower() for s in jd_skills if s and s.strip()}
    s_cand = {s.strip().lower() for s in cand_skills if s and s.strip()}
    if not s_jd or not s_cand:
        return 0.0
    inter = s_jd & s_cand
    union = s_jd | s_cand
    return len(inter) / len(union)


def salary_compat(jd_range: SalaryRange | str | None,
                  cand_range: SalaryRange | str | None) -> float:
    """薪资带宽匹配度 ∈ [0, 1]

    1.0 = 候选人期望区间 ⊆ JD 区间 (或完全重合)
    0.5 = 部分重叠
    0.0 = 完全错位
    0.5 = 任一/双方无信息 (中性)
    """
    if isinstance(jd_range, str):
        jd = parse_range(jd_range)
    else:
        jd = jd_range
    if isinstance(cand_range, str):
        cand = parse_range(cand_range)
    else:
        cand = cand_range

    if jd is None or cand is None:
        return 0.5

    # 内部统一归一到 k 再比较, 避免 yuan vs k 单位错位
    jd = jd.to_kiloyuan()
    cand = cand.to_kiloyuan()

    # 完全包含
    if jd.lo <= cand.lo and cand.hi <= jd.hi:
        return 1.0

    # 部分重叠
    overlap_lo = max(jd.lo, cand.lo)
    overlap_hi = min(jd.hi, cand.hi)
    if overlap_lo < overlap_hi:
        cand_w = cand.width
        if cand_w <= 0:
            return 1.0
        return min(1.0, (overlap_hi - overlap_lo) / cand_w)

    # 完全错位: 算 gap
    # 边界相接 (gap=0) 不算兼容, 直接返 0
    gap = max(jd.lo - cand.hi, cand.lo - jd.hi)
    if gap <= 0:
        return 0.0
    jd_w = jd.width
    if jd_w <= 0:
        return 0.0
    return max(0.0, 1.0 - gap / jd_w)


def years_compat(jd_min_years: int | None, cand_years: int | None) -> float:
    """工作年限匹配度 ∈ [0, 1]

    无要求 (None / 0) → 1.0
    候选人 >= 要求 → 1.0
    不足 → 线性衰减, 差 5 年归 0
    """
    if jd_min_years is None or jd_min_years <= 0:
        return 1.0
    if cand_years is None:
        return 0.5
    if cand_years >= jd_min_years:
        return 1.0
    gap = jd_min_years - cand_years
    return max(0.0, 1.0 - gap * 0.2)


# ==================== 3. 总分 ====================

@dataclass
class MatchResult:
    candidate_id: str
    score: float
    skill_overlap: float
    salary_compat: float
    years_compat: float

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "score": self.score,
            "skill_overlap": self.skill_overlap,
            "salary_compat": self.salary_compat,
            "years_compat": self.years_compat,
        }


# 权重 (TODO: 让权重可配置, 未来可调)
W_SKILL = 0.5
W_SALARY = 0.3
W_YEARS = 0.2


def score_candidate(jd: dict, candidate: dict) -> MatchResult:
    """算 jd 与 candidate 的总匹配分 ∈ [0, 1]

    jd 字段:
      requirements: list[str]   技能集合
      salary_range: str          薪资区间 (raw 文本, parser 内部处理)
      min_years: int             最低工作年限 (None/0 = 不要求)

    candidate 字段:
      skills: list[str]
      expected_salary: str
      years: int
    """
    skill = skill_overlap(jd.get("requirements") or [], candidate.get("skills") or [])
    salary = salary_compat(jd.get("salary_range"), candidate.get("expected_salary"))
    years = years_compat(jd.get("min_years"), candidate.get("years"))

    total = W_SKILL * skill + W_SALARY * salary + W_YEARS * years
    return MatchResult(
        candidate_id=candidate.get("id", candidate.get("candidate_id", "")),
        score=round(total, 3),
        skill_overlap=round(skill, 3),
        salary_compat=round(salary, 3),
        years_compat=round(years, 3),
    )


def rank_candidates(jd: dict, candidates: Iterable[dict]) -> list[MatchResult]:
    """对一组候选人按 score 降序排序"""
    return sorted(
        (score_candidate(jd, c) for c in candidates),
        key=lambda r: r.score,
        reverse=True,
    )
