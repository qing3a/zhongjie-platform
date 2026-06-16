"""
L6 Protocol - AI 路由
端点:
- POST /api/llm/enhance  - 文本润色 (job / service / resume / product)
"""
from fastapi import APIRouter, Depends, HTTPException

from ...ai import EnhanceRequest, LLMError, enhance_text
from ..schemas import EnhanceRequestSchema, EnhanceResponseSchema

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.post("/enhance", response_model=EnhanceResponseSchema)
def enhance_text_endpoint(
    body: EnhanceRequestSchema,
):
    """润色用户输入的文本 (岗位 / 服务 / 简历 / 商品描述)

    默认走 Stub provider (不调真实 API, 适合 dev/test)
    切换真实 LLM: 设环境变量 ZHONGJIE_LLM_PROVIDER=openai, OPENAI_API_KEY=sk-...
    """
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
