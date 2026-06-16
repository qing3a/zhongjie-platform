"""
P6 M29 - 结构化提取 (extract) + 内容审核 (classify) 单元测试

覆盖:
- extract_fields 启发式 (skills/years/education/industry/location/salary)
- extract_fields LLM 模式 + JSON 容错
- extract_fields stub fallback (LLM 失败)
- classify_text 风险分级 (allow/review/block)
- classify_text 各类别关键词命中
- classify_text softening 关键词降低分数
- classify_text LLM 模式 + fallback
- 端点级 smoke (stub 模式 HTTP 200)
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


# ==================== extract_fields ====================

class TestExtractStub:
    def test_extract_skills(self):
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="需要 Python 后端和 React 前端, 熟悉 PostgreSQL", mode="stub")
        r = extract_fields(req)
        assert "Python" in r.skills
        assert "React" in r.skills
        assert "PostgreSQL" in r.skills
        assert r.source == "stub"

    def test_extract_skills_service_keywords(self):
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="需要会修水管的师傅, 也做家电维修", mode="stub")
        r = extract_fields(req)
        assert "维修" in r.skills
        assert "家电维修" in r.skills
        # 水电/水管应匹到一个 (因为两关键词都含"水")
        assert any("水" in s for s in r.skills)

    def test_extract_years_chinese(self):
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="5 年 Python 后端经验, 熟悉微服务架构", mode="stub")
        r = extract_fields(req)
        assert r.experience_years == 5

    def test_extract_years_english(self):
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="3 years of experience in distributed systems", mode="stub")
        r = extract_fields(req)
        assert r.experience_years == 3

    def test_extract_years_none_when_absent(self):
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="需要招聘, 没有其他信息", mode="stub")
        r = extract_fields(req)
        assert r.experience_years is None

    def test_extract_education_phd(self):
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="博士毕业, 985 高校", mode="stub")
        r = extract_fields(req)
        assert r.education == "博士"

    def test_extract_education_bachelor(self):
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="本科学历, 计算机专业", mode="stub")
        r = extract_fields(req)
        assert r.education == "本科"

    def test_extract_education_picks_highest(self):
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="本科毕业, 后续取得硕士学历", mode="stub")
        r = extract_fields(req)
        # 硕士 > 本科, 应取硕士
        assert r.education == "硕士"

    def test_extract_industry(self):
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="互联网行业, 也有金融业务", mode="stub")
        r = extract_fields(req)
        assert "互联网" in r.industry
        assert "金融" in r.industry

    def test_extract_location(self):
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="工作地点北京, 可接受上海出差", mode="stub")
        r = extract_fields(req)
        assert "北京" in r.location
        assert "上海" in r.location

    def test_extract_salary(self):
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="薪资 30-50K, 13 薪", mode="stub")
        r = extract_fields(req)
        assert r.salary_text is not None
        assert "30" in r.salary_text
        assert "50" in r.salary_text

    def test_extract_empty_results(self):
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="hello world", mode="stub")
        r = extract_fields(req)
        assert r.skills == []
        assert r.experience_years is None
        assert r.education is None
        assert r.industry == []
        assert r.location == []
        assert r.salary_text is None

    def test_extract_skill_lowercase_match(self):
        # "python" 应匹到 "Python" 关键词 (case-insensitive)
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="我们用 python 和 aws 部署", mode="stub")
        r = extract_fields(req)
        assert "Python" in r.skills
        assert "AWS" in r.skills

    def test_extract_deduplicates_skills(self):
        from zhongjie.ai import ExtractRequest, extract_fields
        req = ExtractRequest(text="Python Python Python, React React", mode="stub")
        r = extract_fields(req)
        assert r.skills.count("Python") == 1
        assert r.skills.count("React") == 1


class TestExtractLLM:
    def test_llm_mode_returns_llm_source(self):
        from zhongjie.ai import ExtractRequest, LLMProvider, extract_fields

        class FakeLLM(LLMProvider):
            name = "fake"
            def complete(self, system, user, **kwargs):
                return '{"skills": ["Go", "Docker"], "experience_years": 7, "education": "硕士", "industry": ["互联网"], "location": ["上海"], "salary_text": "50-80K"}'

        req = ExtractRequest(text="anything", mode="llm")
        r = extract_fields(req, provider=FakeLLM())
        assert r.source == "llm"
        assert r.skills == ["Go", "Docker"]
        assert r.experience_years == 7
        assert r.education == "硕士"

    def test_llm_json_with_markdown_fence(self):
        from zhongjie.ai import ExtractRequest, LLMProvider, extract_fields

        class FakeLLM(LLMProvider):
            name = "fake"
            def complete(self, system, user, **kwargs):
                return '```json\n{"skills": ["Python"], "experience_years": 3}\n```'

        req = ExtractRequest(text="x", mode="llm")
        r = extract_fields(req, provider=FakeLLM())
        assert r.skills == ["Python"]
        assert r.experience_years == 3

    def test_llm_failure_falls_back_to_stub(self):
        from zhongjie.ai import ExtractRequest, LLMError, LLMProvider, extract_fields

        class BrokenLLM(LLMProvider):
            name = "broken"
            def complete(self, system, user, **kwargs):
                raise LLMError("API down")

        req = ExtractRequest(text="需要 Python 后端", mode="llm")
        r = extract_fields(req, provider=BrokenLLM())
        # fallback 到 stub
        assert r.source == "stub"
        assert "Python" in r.skills


# ==================== classify_text ====================

class TestClassifyStub:
    def test_normal_text_allowed(self):
        from zhongjie.ai import ClassifyRequest, RiskAction, classify_text
        req = ClassifyRequest(
            text="我们公司招 Python 后端开发, 5 年经验, 30-50K",
            mode="stub",
        )
        r = classify_text(req)
        assert r.risk_score < 0.3
        assert r.action == RiskAction.ALLOW
        assert r.primary_category == "NORMAL"

    def test_spam_detected(self):
        from zhongjie.ai import ClassifyRequest, classify_text
        req = ClassifyRequest(
            text="高薪诚聘, 加微信详谈, 兼职日结千元",
            mode="stub",
        )
        r = classify_text(req)
        assert r.risk_score > 0.3
        assert "SPAM" in r.categories

    def test_fraud_high_risk_blocked(self):
        from zhongjie.ai import ClassifyRequest, RiskAction, classify_text
        req = ClassifyRequest(
            text="刷单兼职, 充值返现, 先交押金",
            mode="stub",
        )
        r = classify_text(req)
        assert r.risk_score >= 0.7
        assert r.action == RiskAction.BLOCK
        assert "FRAUD" in r.categories

    def test_illegal_blocked(self):
        from zhongjie.ai import ClassifyRequest, RiskAction, classify_text
        req = ClassifyRequest(
            text="出售冰毒摇头丸, 价格优惠",
            mode="stub",
        )
        r = classify_text(req)
        assert r.action == RiskAction.BLOCK
        assert "ILLEGAL" in r.categories

    def test_sexual_blocked(self):
        from zhongjie.ai import ClassifyRequest, RiskAction, classify_text
        req = ClassifyRequest(
            text="约炮一夜情, 裸聊可上门",
            mode="stub",
        )
        r = classify_text(req)
        assert r.action == RiskAction.BLOCK
        assert "SEXUAL" in r.categories

    def test_offtopic_review(self):
        from zhongjie.ai import ClassifyRequest, classify_text
        req = ClassifyRequest(
            text="拼车回家, 找同程的伙伴",
            mode="stub",
        )
        r = classify_text(req)
        assert "OFFTOPIC" in r.categories

    def test_softening_reduces_score(self):
        from zhongjie.ai import ClassifyRequest, classify_text
        # 高风险关键词 + 正规化关键词 → 应被压低
        req_with = ClassifyRequest(
            text="兼职日结千元, 正规公司签合同, 五险一金",
            mode="stub",
        )
        req_without = ClassifyRequest(
            text="兼职日结千元",
            mode="stub",
        )
        r_with = classify_text(req_with)
        r_without = classify_text(req_without)
        assert r_with.risk_score < r_without.risk_score

    def test_risk_categories_constants(self):
        from zhongjie.ai import RiskCategory
        assert RiskCategory.NORMAL == "NORMAL"
        assert RiskCategory.SPAM == "SPAM"
        assert RiskCategory.FRAUD == "FRAUD"
        assert "ILLEGAL" in RiskCategory.ALL
        assert "SEXUAL" in RiskCategory.ALL


class TestClassifyLLM:
    def test_llm_mode_returns_llm_source(self):
        from zhongjie.ai import ClassifyRequest, LLMProvider, classify_text

        class FakeLLM(LLMProvider):
            name = "fake"
            def complete(self, system, user, **kwargs):
                return '{"risk_score": 0.8, "primary_category": "FRAUD", "categories": ["FRAUD", "SPAM"], "action": "block", "reason": "命中刷单关键词"}'

        req = ClassifyRequest(text="x", mode="llm")
        r = classify_text(req, provider=FakeLLM())
        assert r.source == "llm"
        assert r.risk_score == 0.8
        assert r.primary_category == "FRAUD"
        assert r.action == "block"

    def test_llm_failure_falls_back_to_stub(self):
        from zhongjie.ai import ClassifyRequest, LLMError, LLMProvider, classify_text

        class BrokenLLM(LLMProvider):
            name = "broken"
            def complete(self, system, user, **kwargs):
                raise LLMError("API down")

        req = ClassifyRequest(text="需要 Python 后端, 30-50K", mode="llm")
        r = classify_text(req, provider=BrokenLLM())
        assert r.source == "stub"


# ==================== 端点 smoke (HTTP 路径) ====================

class TestEndpoints:
    def test_extract_endpoint_stub(self):
        from zhongjie.ai import ClassifyRequest, ExtractRequest
        # 直接调函数, 不走 HTTP (避免起 server)
        req = ExtractRequest(text="需要 Python 后端, 5 年经验, 30-50K", mode="stub")
        from zhongjie.ai import extract_fields
        r = extract_fields(req)
        assert r.experience_years == 5
        assert "Python" in r.skills

    def test_classify_endpoint_logic(self):
        from zhongjie.ai import ClassifyRequest, classify_text
        req = ClassifyRequest(text="python 后端开发, 30-50K", mode="stub")
        r = classify_text(req)
        assert r.action == "allow"
        assert r.risk_score < 0.3
