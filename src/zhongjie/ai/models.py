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
