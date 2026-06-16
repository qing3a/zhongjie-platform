"""
L7 AI - 输入输出数据模型 (Pydantic)
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class EnhanceRequest(BaseModel):
    """文本润色请求
    text: 用户原始输入 (口语化/粗糙)
    category: 信息类别 (job / service / resume / product)
    temperature: 0-1, 默认 0.3 (稳)
    """
    text: str = Field(..., min_length=1, max_length=10_000)
    category: str | None = None
    temperature: float = Field(default=0.3, ge=0.0, le=1.0)


class EnhanceResult(BaseModel):
    """文本润色结果"""
    request_id: str
    original_text: str
    enhanced_text: str
    tags: list[str] = Field(default_factory=list)
    provider: str        # "stub" / "openai" / "anthropic"
    model: str
    latency_ms: int | None = None


# ============ Extract (v0.3) ============

class ExtractRequest(BaseModel):
    """结构化提取请求"""
    text: str = Field(..., min_length=1, max_length=20_000)
    schema_hint: str | None = None  # "resume" / "jd" / "service_request" / None
    mode: str = Field(default="auto")  # "auto" | "stub" | "llm"


class ExtractResult(BaseModel):
    """结构化提取结果"""
    request_id: str
    raw_text: str
    source: str          # "stub" / "llm"
    provider: str
    model: str
    latency_ms: int | None = None
    # 抽取字段 — 全部 Optional, 不同 schema_hint 字段不同
    skills: list[str] = Field(default_factory=list)
    experience_years: int | None = None
    education: str | None = None
    industry: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)
    salary_text: str | None = None  # 原文片段, 进一步 parse 走 domain/matching.py
    # LLM 模式可返回的额外字段
    extras: dict = Field(default_factory=dict)


# ============ Classify (v0.3) ============

class ClassifyRequest(BaseModel):
    """内容审核请求"""
    text: str = Field(..., min_length=1, max_length=20_000)
    context: str | None = None  # "jd" / "post" / "candidate_claim" / None
    mode: str = Field(default="auto")  # "auto" | "stub" | "llm"


class ClassifyResult(BaseModel):
    """内容审核结果"""
    request_id: str
    text_preview: str    # 前 100 字 (避免长 text 重复)
    risk_score: float    # 0-1
    primary_category: str
    categories: list[str]
    action: str          # "allow" | "review" | "block"
    reason: str
    provider: str
    model: str
    source: str          # "stub" / "llm"
