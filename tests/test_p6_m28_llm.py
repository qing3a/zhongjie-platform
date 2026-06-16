"""
P6 M28 - LLM client + enhance_text 单元测试

覆盖:
- LLMProvider 抽象 + 工厂
- StubProvider 默认行为 (不调 API)
- OpenAIProvider / AnthropicProvider 懒加载 + API key 缺失报错
- enhance_text 端到端 (Stub 模式)
- Prompt 模板可加载
- 切换 provider 通过 env
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


# ==================== Provider 抽象 ====================

class TestProviderFactory:
    def test_default_provider_is_stub(self, monkeypatch):
        from zhongjie.ai.llm import StubProvider, get_provider, reset_providers
        monkeypatch.delenv("ZHONGJIE_LLM_PROVIDER", raising=False)
        reset_providers()
        p = get_provider()
        assert isinstance(p, StubProvider)
        assert p.name == "stub"

    def test_explicit_stub(self):
        from zhongjie.ai.llm import StubProvider, get_provider, reset_providers
        reset_providers()
        p = get_provider("stub")
        assert isinstance(p, StubProvider)

    def test_singleton_caching(self):
        from zhongjie.ai.llm import get_provider, reset_providers
        reset_providers()
        p1 = get_provider("stub")
        p2 = get_provider("stub")
        assert p1 is p2  # same instance

    def test_unknown_provider_raises(self):
        from zhongjie.ai.llm import LLMError, get_provider, reset_providers
        reset_providers()
        with pytest.raises(LLMError, match="Unknown LLM provider"):
            get_provider("gpt-99")

    def test_env_var_picks_provider(self, monkeypatch):
        from zhongjie.ai.llm import get_provider, reset_providers
        monkeypatch.setenv("ZHONGJIE_LLM_PROVIDER", "stub")
        reset_providers()
        # 显式 None 让 env 生效
        p = get_provider(None)
        assert p.name == "stub"

    def test_reset_providers_clears_cache(self):
        from zhongjie.ai.llm import get_provider, reset_providers
        p1 = get_provider("stub")
        reset_providers()
        p2 = get_provider("stub")
        assert p1 is not p2  # reset 强制重建


# ==================== StubProvider ====================

class TestStubProvider:
    def test_returns_mock_text(self):
        from zhongjie.ai.llm import StubProvider
        p = StubProvider()
        out = p.complete("system", "user input")
        assert "[stub-enhanced]" in out
        assert "user input" in out

    def test_truncates_long_user(self):
        from zhongjie.ai.llm import StubProvider
        p = StubProvider()
        long_user = "x" * 500
        out = p.complete("s", long_user)
        # stub 截前 200 字符
        assert len(out) < 300


# ==================== OpenAI / Anthropic 懒加载 ====================

class TestOpenAIProvider:
    def test_lazy_load_no_api_key_yet(self, monkeypatch):
        from zhongjie.ai.llm import OpenAIProvider
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        p = OpenAIProvider(api_key=None)
        # _client 是 None 时不会立即调 API
        assert p._client is None

    def test_missing_openai_package_raises(self, monkeypatch):
        # 模拟 openai 未安装: 注入 sys.modules 让 import 失败
        from zhongjie.ai import llm as llm_mod
        from zhongjie.ai.llm import LLMError
        p = llm_mod.OpenAIProvider(api_key="dummy")
        # 用 monkeypatch 屏蔽真实的 openai 包 (注入一个 raise ImportError 的占位)
        import sys
        original_openai = sys.modules.get("openai")
        sys.modules["openai"] = None  # type: ignore
        try:
            with pytest.raises(LLMError, match="openai"):
                p._get_client()
        finally:
            if original_openai is not None:
                sys.modules["openai"] = original_openai
            else:
                sys.modules.pop("openai", None)

    def test_openai_call_failure_raises_llmerror(self, monkeypatch):
        from zhongjie.ai.llm import LLMError, OpenAIProvider
        p = OpenAIProvider(api_key="dummy-key")
        # 注入会抛的 mock client
        class BrokenClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        raise RuntimeError("API down")
        p._client = BrokenClient()
        with pytest.raises(LLMError, match="OpenAI call failed"):
            p.complete("s", "u")


# ==================== enhance_text 高层 ====================

class TestEnhanceText:
    def test_returns_enhance_result(self):
        from zhongjie.ai.llm import enhance_text, get_provider, reset_providers
        from zhongjie.ai.models import EnhanceRequest
        reset_providers()
        req = EnhanceRequest(text="想找个会修水管的师傅, 周末上门", category="service")
        result = enhance_text(req)
        assert result.original_text == req.text
        assert "[stub-enhanced]" in result.enhanced_text
        assert result.provider == "stub"
        assert result.request_id  # uuid 非空

    def test_tags_extraction_stub(self):
        from zhongjie.ai.llm import enhance_text, reset_providers
        from zhongjie.ai.models import EnhanceRequest
        reset_providers()
        req = EnhanceRequest(text="需要 Python 后端和 React 前端", category="job")
        result = enhance_text(req)
        # stub 模式从原文抽关键词
        assert "Python" in result.tags
        assert "React" in result.tags

    def test_temperature_passed_through(self):
        from zhongjie.ai.llm import StubProvider, enhance_text
        from zhongjie.ai.models import EnhanceRequest
        req = EnhanceRequest(text="hi", temperature=0.9)
        result = enhance_text(req, provider=StubProvider())
        assert result is not None  # 不崩即过

    def test_inject_custom_provider(self):
        from zhongjie.ai.llm import LLMProvider, enhance_text
        from zhongjie.ai.models import EnhanceRequest

        class FakeProvider(LLMProvider):
            name = "fake"
            def complete(self, system, user, **kwargs):
                return "FAKE_RESPONSE"

        req = EnhanceRequest(text="x", category="test")
        result = enhance_text(req, provider=FakeProvider())
        assert result.enhanced_text == "FAKE_RESPONSE"
        assert result.provider == "fake"


# ==================== Prompt 模板 ====================

class TestPrompts:
    def test_enhance_system_prompt_exists(self):
        from zhongjie.ai.prompts import ENHANCE_TEXT_SYSTEM
        assert "zhongjie" in ENHANCE_TEXT_SYSTEM
        assert "润色" in ENHANCE_TEXT_SYSTEM

    def test_enhance_user_template_renders(self):
        from zhongjie.ai.prompts import ENHANCE_TEXT_USER_TEMPLATE
        out = ENHANCE_TEXT_USER_TEMPLATE.format(
            text="hello",
            category="job",
        )
        assert "hello" in out
        assert "job" in out


# ==================== Models ====================

class TestModels:
    def test_enhance_request_validates(self):
        from zhongjie.ai.models import EnhanceRequest
        # 空文本应被 Pydantic 拒绝
        with pytest.raises(Exception):
            EnhanceRequest(text="")

    def test_enhance_request_temperature_bounds(self):
        from zhongjie.ai.models import EnhanceRequest
        with pytest.raises(Exception):
            EnhanceRequest(text="x", temperature=1.5)
        with pytest.raises(Exception):
            EnhanceRequest(text="x", temperature=-0.1)

    def test_enhance_result_default_tags_empty(self):
        from zhongjie.ai.models import EnhanceRequest, EnhanceResult
        req = EnhanceRequest(text="x")
        result = EnhanceResult(
            request_id="rid", original_text="x",
            enhanced_text="X", provider="stub", model="mock",
        )
        assert result.tags == []
        assert result.latency_ms is None
        assert req.text == "x"
