"""
L7 AI - Layer 包占位

本包是 v0.3.0 重定位后的核心新增 (AI 协作平台):
- llm.py: provider-agnostic LLM client (openai/anthropic/stub)
- prompts.py: prompt 模板
- models.py: Pydantic 输入输出

后续 (v0.3.1+):
- embedding.py: 文本 embedding
- agent.py: agent loop + tool use
- classify.py: 内容审核 / 风险分类
"""
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
from .models import EnhanceRequest, EnhanceResult

__all__ = [
    "LLMProvider",
    "LLMError",
    "StubProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "get_provider",
    "reset_providers",
    "enhance_text",
    "EnhanceRequest",
    "EnhanceResult",
]
