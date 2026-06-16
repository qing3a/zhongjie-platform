"""
L6 Protocol - AI 路由
端点:
- POST /api/llm/enhance   - 文本润色 (job / service / resume / product)
- POST /api/llm/extract   - 结构化字段提取 (skills / years / education / etc.)
- POST /api/llm/classify  - 内容审核 (risk_score / categories / action)
"""
from fastapi import APIRouter, HTTPException

from ...ai import (
    ClassifyRequest,
    EnhanceRequest,
    ExtractRequest,
    LLMError,
    RiskAction,
    classify_text,
    enhance_text,
    extract_fields,
)
from ..schemas import (
    ClassifyRequestSchema,
    ClassifyResponseSchema,
    EnhanceRequestSchema,
    EnhanceResponseSchema,
    ExtractRequestSchema,
    ExtractResponseSchema,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.post("/enhance", response_model=EnhanceResponseSchema)
def enhance_text_endpoint(body: EnhanceRequestSchema):
    """润色用户输入的文本 (岗位 / 服务 / 简历 / 商品描述)"""
    req = EnhanceRequest(
        text=body.text,
        category=body.category,
        temperature=body.temperature,
    )
    try:
        result = enhance_text(req)
    except LLMError as e:
        raise HTTPException(503, f"LLM provider error: {e}")
    return EnhanceResponseSchema(
        request_id=result.request_id,
        enhanced_text=result.enhanced_text,
        tags=result.tags,
        provider=result.provider,
        model=result.model,
    )


@router.post("/extract", response_model=ExtractResponseSchema)
def extract_fields_endpoint(body: ExtractRequestSchema):
    """从自由文本提取结构化字段

    用于: 简历解析 / JD 理解 / 服务需求结构化
    端点: POST /api/llm/extract {text, schema_hint?, mode?}
    """
    req = ExtractRequest(
        text=body.text,
        schema_hint=body.schema_hint,
        mode=body.mode,
    )
    try:
        result = extract_fields(req)
    except LLMError as e:
        raise HTTPException(503, f"LLM provider error: {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return ExtractResponseSchema(
        request_id=result.request_id,
        source=result.source,
        provider=result.provider,
        model=result.model,
        skills=result.skills,
        experience_years=result.experience_years,
        education=result.education,
        industry=result.industry,
        location=result.location,
        salary_text=result.salary_text,
        extras=result.extras,
    )


@router.post("/classify", response_model=ClassifyResponseSchema)
def classify_text_endpoint(body: ClassifyRequestSchema):
    """内容审核 (风险分级 + 类别)

    action:
      - "allow"   (risk < 0.3)  放行
      - "review"  (0.3-0.7)    进人工二审队列
      - "block"   (>= 0.7)     拒绝, 通知用户
    """
    req = ClassifyRequest(
        text=body.text,
        context=body.context,
        mode=body.mode,
    )
    try:
        result = classify_text(req)
    except LLMError as e:
        raise HTTPException(503, f"LLM provider error: {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    # 二次校验: action 和 risk_score 的一致性
    if result.risk_score >= 0.7 and result.action != RiskAction.BLOCK:
        # 异常 — LLM 返了不一致的值, 强制 block
        result.action = RiskAction.BLOCK
    elif result.risk_score < 0.3 and result.action == RiskAction.BLOCK:
        result.action = RiskAction.ALLOW
    return ClassifyResponseSchema(
        request_id=result.request_id,
        text_preview=result.text_preview,
        risk_score=result.risk_score,
        primary_category=result.primary_category,
        categories=result.categories,
        action=result.action,
        reason=result.reason,
        provider=result.provider,
        model=result.model,
        source=result.source,
    )
