"""
L7 AI - LLM client (provider-agnostic) + 第一个能力: 文本润色

设计原则:
- 不绑定任何特定 LLM 供应商 (OpenAI / Anthropic / 国产 / 本地都可换)
- 默认 stub 模式 (不调 API, 返回 mock), 让测试和 dev 不需要 API key
- 通过 env 切换 provider: ZHONGJIE_LLM_PROVIDER=openai|stub|anthropic
- 同步接口 (没有 async 复杂度) — FastAPI threadpool 已够用

限制 (TODO v0.3.1+):
- 没有 streaming (用 LLM 一次性返回)
- 没有 retry (上层调用方决定)
- 没有 token 计数 / cost 跟踪
- 没有 caching (同一 prompt 调多次)
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import Callable
from typing import Any

from .models import EnhanceRequest, EnhanceResult
from .prompts import ENHANCE_TEXT_SYSTEM, ENHANCE_TEXT_USER_TEMPLATE

logger = logging.getLogger(__name__)


# ==================== Provider 抽象 ====================

class LLMProvider:
    """LLM 供应商基类
    子类: OpenAIProvider, AnthropicProvider, StubProvider
    """
    name: str = "base"

    def complete(self, system: str, user: str, *, model: str | None = None,
                 temperature: float = 0.3, max_tokens: int = 1000) -> str:
        """返回模型原始输出 (纯文本)
        raise LLMError on failure
        """
        raise NotImplementedError


class LLMError(Exception):
    """LLM 调用失败 (网络/限流/超时)"""
    pass


# ==================== Stub Provider (默认, 不调 API) ====================

class StubProvider(LLMProvider):
    name = "stub"

    def complete(self, system: str, user: str, *, model: str | None = None,
                 temperature: float = 0.3, max_tokens: int = 1000) -> str:
        # 模拟延迟 (10-50ms, 让 dev 体验更真实)
        time.sleep(0.01)
        # 简单启发式 mock:
        # 润色: 把输入原样 + 简单标签回返
        return f"[stub-enhanced] {user[:200]}"


# ==================== OpenAI Provider ====================

class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str | None = None, default_model: str = "gpt-4o-mini") -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._default_model = default_model
        self._client: Any = None  # 懒加载

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise LLMError(
                    "openai package not installed. `pip install openai` first."
                ) from e
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def complete(self, system: str, user: str, *, model: str | None = None,
                 temperature: float = 0.3, max_tokens: int = 1000) -> str:
        try:
            client = self._get_client()
            resp = client.chat.completions.create(
                model=model or self._default_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            raise LLMError(f"OpenAI call failed: {e}") from e


# ==================== Anthropic Provider (TODO) ====================

class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None = None, default_model: str = "claude-3-5-sonnet-20241022") -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._default_model = default_model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from anthropic import Anthropic
            except ImportError as e:
                raise LLMError(
                    "anthropic package not installed. `pip install anthropic` first."
                ) from e
            self._client = Anthropic(api_key=self._api_key)
        return self._client

    def complete(self, system: str, user: str, *, model: str | None = None,
                 temperature: float = 0.3, max_tokens: int = 1000) -> str:
        try:
            client = self._get_client()
            resp = client.messages.create(
                model=model or self._default_model,
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            # Anthropic 返回 content blocks, 第一个 text block
            return resp.content[0].text if resp.content else ""
        except Exception as e:
            raise LLMError(f"Anthropic call failed: {e}") from e


# ==================== 工厂 ====================

_PROVIDER_CACHE: dict[str, LLMProvider] = {}


def get_provider(name: str | None = None) -> LLMProvider:
    """获取 LLM provider 单例
    name 优先级: 参数 > env ZHONGJIE_LLM_PROVIDER > "stub"
    """
    name = name or os.environ.get("ZHONGJIE_LLM_PROVIDER", "stub")
    if name not in _PROVIDER_CACHE:
        if name == "stub":
            _PROVIDER_CACHE[name] = StubProvider()
        elif name == "openai":
            _PROVIDER_CACHE[name] = OpenAIProvider()
        elif name == "anthropic":
            _PROVIDER_CACHE[name] = AnthropicProvider()
        else:
            raise LLMError(f"Unknown LLM provider: {name!r}. "
                            f"Use: stub | openai | anthropic")
    return _PROVIDER_CACHE[name]


def reset_providers() -> None:
    """测试隔离: 清 provider 缓存"""
    _PROVIDER_CACHE.clear()


# ==================== 第一个高层能力: 文本润色 ====================

def enhance_text(req: EnhanceRequest, *,
                 provider: LLMProvider | None = None) -> EnhanceResult:
    """润色用户输入的文本 (岗位描述 / 服务描述 / 简历亮点)

    返回结构化结果: enhanced_text + 提取的标签 + 风险提示
    Stub 模式: enhanced_text 是 "[stub-enhanced] <原文本前200字符>", tags=[]
    """
    provider = provider or get_provider()
    system = ENHANCE_TEXT_SYSTEM
    user = ENHANCE_TEXT_USER_TEMPLATE.format(
        text=req.text,
        category=req.category or "通用",
    )
    try:
        raw = provider.complete(system, user, temperature=req.temperature)
    except LLMError as e:
        logger.warning(f"enhance_text LLM call failed: {e}, fallback to stub")
        raw = f"[stub-fallback] {req.text[:200]}"

    # 简单结构化: 真实 LLM 返 JSON, stub 返纯文本
    # TODO v0.3.1: 强约束 LLM 返 JSON (response_format={"type":"json_object"})
    enhanced_text = raw.strip()
    tags = _extract_tags_stub(raw) if provider.name == "stub" else []

    # 取 model 标识: OpenAI/Anthropic 各自有 _default_model, Stub 用 "stub-v1"
    model_id = getattr(provider, "_default_model", None) or f"{provider.name}-v1"

    return EnhanceResult(
        request_id=str(uuid.uuid4()),
        original_text=req.text,
        enhanced_text=enhanced_text,
        tags=tags,
        provider=provider.name,
        model=model_id,
        latency_ms=None,  # TODO: 计时
    )


def _extract_tags_stub(text: str) -> list[str]:
    """Stub 模式的标签提取: 简单关键词 (后续用 LLM 替代)"""
    keywords = []
    for word in ("Python", "Java", "Go", "AI", "React", "Vue", "AWS", "招聘", "家政", "维修"):
        if word in text:
            keywords.append(word)
    return keywords[:10]


# ==================== 公开 API ====================

__all__ = [
    "LLMProvider",
    "LLMError",
    "StubProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "get_provider",
    "reset_providers",
    "enhance_text",
]
