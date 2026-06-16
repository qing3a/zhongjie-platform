"""
L7 AI - 结构化字段提取 (extract)

从自由文本中提取结构化字段 (技能 / 工作年限 / 薪资区间 / 学历 / 行业)
用于简历解析、JD 理解、服务需求结构化 — zhongjie 数据可比性的基础。

设计:
- 输入: 自由文本 (resume_text / jd_text / service_request)
- 输出: ExtractResult (skills, experience_years, education, salary_range, location, ...)
- 实现:
  - LLM 模式: prompt + 强约束 JSON 输出 (response_format={"type":"json_object"} for OpenAI)
  - Stub 模式: 关键词表 + 正则抽取 (复用 domain/matching.py 的 salary 解析)

非目标 (v0.3):
- 不做 PDF/Word 解析 (那是 ai/parse_resume.py 后续工作)
- 不做语义实体抽取 (用 embedding + NER, v0.3.1+)
- 不做错误纠正 (LLM 自己负责, 我们的 schema 校验兜底)
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from typing import Any

from .llm import LLMError, LLMProvider, get_provider
from .models import ExtractRequest, ExtractResult
from .prompts import EXTRACT_SYSTEM, EXTRACT_USER_TEMPLATE

logger = logging.getLogger(__name__)


# ==================== Stub 模式关键词表 (复用 matching.py) ====================

# 技能关键词 (与 domain/matching.py skill_overlap 共用)
SKILL_KEYWORDS = [
    # 编程语言
    "Python", "Java", "Go", "Rust", "C++", "C#", "JavaScript", "TypeScript",
    "Ruby", "PHP", "Swift", "Kotlin", "Scala",
    # 框架
    "React", "Vue", "Angular", "Django", "Flask", "FastAPI", "Spring", "Rails",
    "Next.js", "Nuxt", "Express", "NestJS",
    # 数据 / AI
    "PyTorch", "TensorFlow", "Pandas", "NumPy", "Spark", "Hadoop", "Kafka",
    "LLM", "RAG", "Agent", "Embedding",
    # 基础设施
    "AWS", "Azure", "GCP", "Docker", "Kubernetes", "PostgreSQL", "MySQL",
    "MongoDB", "Redis", "Elasticsearch",
    # 本地生活服务
    "家政", "保洁", "月嫂", "育婴", "养老", "护理",
    "维修", "水电", "水管", "水管工", "管道疏通", "通下水",
    "木工", "瓦工", "油漆", "家电维修", "空调清洗",
    "搬家", "货运", "配送",
    "家教", "陪练", "培训",
    "美甲", "美容", "美发", "美睫", "化妆", "SPA", "瘦身",
    "健身", "瑜伽", "私教",
    "宠物", "兽医", "寄养", "美容师",
]

# 学历关键词
EDUCATION_KEYWORDS = [
    ("博士", 5), ("PhD", 5), ("Ph.D", 5),
    ("硕士", 4), ("研究生", 4), ("Master", 4),
    ("本科", 3), ("学士", 3), ("Bachelor", 3), ("大学", 3),
    ("大专", 2), ("专科", 2), ("College", 2),
    ("高中", 1), ("中专", 1), ("职高", 1), ("High School", 1),
]

# 行业关键词
INDUSTRY_KEYWORDS = [
    "互联网", "IT", "软件", "金融", "银行", "证券", "保险", "基金",
    "教育", "医疗", "医药", "医院", "生物", "健康",
    "电商", "零售", "消费品", "贸易", "物流",
    "制造", "汽车", "机械", "电子", "半导体", "硬件",
    "房地产", "建筑", "装修",
    "媒体", "广告", "公关", "影视", "游戏",
    "咨询", "法律", "会计", "审计", "人力资源",
    "本地生活", "家政服务", "维修服务", "餐饮", "酒店", "旅游",
]

# 地点关键词 (中国主要城市)
LOCATION_KEYWORDS = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "南京", "武汉",
    "苏州", "西安", "重庆", "天津", "长沙", "郑州", "青岛", "东莞",
    "宁波", "佛山", "合肥", "厦门", "福州", "济南", "无锡", "沈阳",
    "远程", "Remote", "在家",
]


# ==================== 启发式抽取函数 ====================

def _extract_skills_stub(text: str) -> list[str]:
    """从文本中找技能关键词
    复用 matching.py 的 lowercase + 前后空格 trim 风格
    """
    text_lower = text.lower()
    found: list[str] = []
    for kw in SKILL_KEYWORDS:
        if kw.lower() in text_lower and kw not in found:
            found.append(kw)
    return found[:20]


def _extract_years_stub(text: str) -> int | None:
    """从文本中找工作年限
    模式: "X 年", "X years", "Xyear" (前后中英文)
    """
    patterns = [
        r"(\d+)\s*年(?:以上|经验|工作)?",
        r"(\d+)\s*years?(?:\s+of)?(?:\s+experience)?",
        r"(\d+)\s*年(?:半)?",  # 半年也算 0.5, 暂只取整数
    ]
    candidates: list[int] = []
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            try:
                v = int(m.group(1))
                if 0 <= v <= 50:  # sanity
                    candidates.append(v)
            except ValueError:
                pass
    if not candidates:
        return None
    # 取最大 (通常 "3 年经验" 比 "刚毕业 0 年" 更代表资历)
    return max(candidates)


def _extract_education_stub(text: str) -> str | None:
    """从文本中找最高学历 (按 EDUCATION_KEYWORDS 排序)"""
    text_lower = text.lower()
    best: tuple[str, int] | None = None
    for kw, level in EDUCATION_KEYWORDS:
        if kw.lower() in text_lower:
            if best is None or level > best[1]:
                best = (kw, level)
    return best[0] if best else None


def _extract_industry_stub(text: str) -> list[str]:
    """从文本中找行业关键词"""
    found: list[str] = []
    for kw in INDUSTRY_KEYWORDS:
        if kw in text and kw not in found:
            found.append(kw)
    return found[:5]


def _extract_location_stub(text: str) -> list[str]:
    """从文本中找地点关键词"""
    found: list[str] = []
    for city in LOCATION_KEYWORDS:
        if city in text and city not in found:
            found.append(city)
    return found[:3]


def _extract_salary_stub(text: str) -> str | None:
    """从文本中找薪资描述
    复用 domain/matching.py 的 parse_range 逻辑 — 但 stub 阶段只做简单匹配
    """
    patterns = [
        r"\d+\s*[-~到至]\s*\d+\s*[Kk万]",
        r"\d+\s*[Kk万]",
        r"月薪\s*\d+",
        r"年薪\s*\d+",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(0)
    return None


# ==================== 主入口 ====================

def extract_fields(req: ExtractRequest, *,
                   provider: LLMProvider | None = None,
                   field_extractors: dict[str, Callable[[str], Any]] | None = None) -> ExtractResult:
    """从自由文本提取结构化字段

    LLM 模式: 一次性 prompt + JSON 输出
    Stub 模式: 5 个独立启发式抽取器 (skills / years / education / industry / location / salary)
    """
    provider = provider or get_provider()
    text = req.text
    mode = req.mode  # "auto" | "stub" | "llm"

    # Stub 模式 (或 LLM 失败 fallback)
    if mode == "stub" or (mode == "auto" and provider.name == "stub"):
        return _extract_stub(text, field_extractors)

    # LLM 模式
    if mode in ("llm", "auto"):
        try:
            system = EXTRACT_SYSTEM
            user = EXTRACT_USER_TEMPLATE.format(
                text=text,
                schema_hint=req.schema_hint or "通用",
            )
            raw = provider.complete(
                system, user,
                temperature=0.0,  # 提取任务用 0 温度保稳定
                max_tokens=1500,
            )
            parsed = _parse_llm_json(raw)
            return ExtractResult(
                request_id=str(uuid.uuid4()),
                raw_text=text,
                provider=provider.name,
                model=getattr(provider, "_default_model", None) or f"{provider.name}-v1",
                latency_ms=None,
                source="llm",
                **parsed,
            )
        except (LLMError, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"extract_fields LLM call failed: {e}, fallback to stub")
            return _extract_stub(text, field_extractors)

    raise ValueError(f"Unknown mode: {mode!r}")


def _extract_stub(text: str,
                  field_extractors: dict[str, Callable[[str], Any]] | None = None) -> ExtractResult:
    """Stub 模式: 5 个独立启发式
    field_extractors 参数用于测试注入, 生产不用
    """
    extractors = field_extractors or {
        "skills": _extract_skills_stub,
        "experience_years": _extract_years_stub,
        "education": _extract_education_stub,
        "industry": _extract_industry_stub,
        "location": _extract_location_stub,
        "salary_text": _extract_salary_stub,
    }
    result_fields: dict[str, Any] = {}
    for name, fn in extractors.items():
        try:
            result_fields[name] = fn(text)
        except Exception as e:
            logger.warning(f"stub extractor {name} failed: {e}")
            result_fields[name] = None

    return ExtractResult(
        request_id=str(uuid.uuid4()),
        raw_text=text,
        provider="stub",
        model="stub-v1",
        latency_ms=None,
        source="stub",
        **result_fields,
    )


def _parse_llm_json(raw: str) -> dict:
    """从 LLM 输出解析 JSON
    容忍: ```json 包裹 / 前后空白 / 多余文本
    """
    raw = raw.strip()
    # 去 markdown fence
    if raw.startswith("```"):
        # 找首个换行后到最后一个 ```
        lines = raw.split("\n", 1)
        if len(lines) > 1:
            raw = lines[1]
        if raw.endswith("```"):
            raw = raw[:-3]
    raw = raw.strip()
    # 找首个 { 到末尾
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    return json.loads(raw)


__all__ = [
    "extract_fields",
    "SKILL_KEYWORDS",
    "EDUCATION_KEYWORDS",
    "INDUSTRY_KEYWORDS",
    "LOCATION_KEYWORDS",
    "_extract_skills_stub",
    "_extract_years_stub",
    "_extract_education_stub",
    "_extract_industry_stub",
    "_extract_location_stub",
    "_extract_salary_stub",
]
