"""
L7 AI - Layer 包占位

本包是 v0.3.0 重定位后的核心新增 (AI 协作平台):
- llm.py: provider-agnostic LLM client (openai/anthropic/stub)
- prompts.py: prompt 模板
- models.py: Pydantic 输入输出
- extract.py: 结构化字段提取 (P0, 简历/JD/服务需求)
- classify.py: 内容审核 (P0, 风险分级 + 类别)

后续 (v0.3.1+):
- embedding.py: 文本 embedding
- agent.py: agent loop + tool use
"""
from .classify import (
    RISK_KEYWORDS,
    SOFTENING_KEYWORDS,
    RiskAction,
    RiskCategory,
    classify_text,
)
from .extract import (
    EDUCATION_KEYWORDS,
    INDUSTRY_KEYWORDS,
    LOCATION_KEYWORDS,
    SKILL_KEYWORDS,
    extract_fields,
)
from .llm import (
    AnthropicProvider,
    LLMError,
    LLMProvider,
    OpenAIProvider,
    StubProvider,
    enhance_text,
    get_provider,
    reset_providers,
)
from .models import (
    ClassifyRequest,
    ClassifyResult,
    EnhanceRequest,
    EnhanceResult,
    ExtractRequest,
    ExtractResult,
)

__all__ = [
    # llm
    "LLMProvider",
    "LLMError",
    "StubProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "get_provider",
    "reset_providers",
    "enhance_text",
    # models
    "EnhanceRequest",
    "EnhanceResult",
    "ExtractRequest",
    "ExtractResult",
    "ClassifyRequest",
    "ClassifyResult",
    # extract
    "extract_fields",
    "SKILL_KEYWORDS",
    "EDUCATION_KEYWORDS",
    "INDUSTRY_KEYWORDS",
    "LOCATION_KEYWORDS",
    # classify
    "classify_text",
    "RiskCategory",
    "RiskAction",
    "RISK_KEYWORDS",
    "SOFTENING_KEYWORDS",
]
