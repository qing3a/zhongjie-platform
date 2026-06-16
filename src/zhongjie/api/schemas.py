"""
API Schemas (Pydantic 请求/响应模型)
"""
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


# ============ Agent ============
class AgentRegisterRequest(BaseModel):
    name: str
    role: Literal["headhunter", "employer", "platform"] = "headhunter"
    capabilities: list[str] = Field(default_factory=list)
    tier: Literal["standard", "silver", "gold"] = "standard"
    endpoint: str | None = None
    description: str = ""


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    role: str
    capabilities: list[str]
    tier: str
    trust_score: float
    status: str
    endpoint: str | None = None
    description: str = ""
    created_at: str = ""


class AgentListResponse(BaseModel):
    agents: list[AgentResponse]
    total: int
    by_role: dict[str, int] = Field(default_factory=dict)


# ============ Task ============
class TaskSendRequest(BaseModel):
    kind: str
    payload: dict = Field(default_factory=dict)
    context_id: str | None = None


class TaskResponse(BaseModel):
    task_id: str
    context_id: str | None
    state: str
    kind: str
    owner_agent_id: str | None
    payload: dict
    history: list[dict] = Field(default_factory=list)
    result: Any = None
    error: str | None = None
    created_at: str
    updated_at: str


# ============ Delegation ============
class DelegationCreateRequest(BaseModel):
    from_agent_id: str
    to_agent_id: str
    candidate_ref: str
    jd_context: str = ""
    fee_split: list[dict] = Field(default_factory=list)
    visibility: Literal["masked", "full"] = "masked"
    deadline: str | None = None
    note: str = ""


class FeeShareRequest(BaseModel):
    agent_id: str
    pct: float
    role: str = "co_finder"


class DelegationResponse(BaseModel):
    id: str
    task_id: str | None
    from_agent_id: str
    to_agent_id: str
    candidate_ref: str
    jd_context: str
    status: str
    fee_split: list[dict]
    visibility: str
    deadline: str | None
    created_at: str
    decided_at: str | None


# ============ Billing ============
class InvoiceCreateRequest(BaseModel):
    delegation_id: str
    candidate_ref: str
    total_amount: float
    fee_split: list[dict]
    currency: str = "CNY"
    note: str = ""


class InvoiceResponse(BaseModel):
    id: str
    delegation_id: str
    candidate_ref: str
    total_amount: float
    currency: str
    status: str
    lines: list[dict]
    created_at: str
    settled_at: str | None


# ============ Trust / Audit ============
class TrustAdjustRequest(BaseModel):
    delta: float
    reason: str = ""


class TrustHistoryEntry(BaseModel):
    agent_id: str
    event_type: str
    delta: float
    new_score: float | None
    timestamp: str
    reason: str = ""


class AuditEntryResponse(BaseModel):
    id: str
    request_id: str
    owner_agent_id: str | None
    decision: str
    matched_rule: str | None
    trust_score: float | None
    timestamp: str
    hash: str
    prev_hash: str
    note: str = ""


# ============ AI / LLM (v0.3 新增) ============
class EnhanceRequestSchema(BaseModel):
    text: str = Field(..., min_length=1, max_length=10_000)
    category: str | None = None
    temperature: float = Field(default=0.3, ge=0.0, le=1.0)


class EnhanceResponseSchema(BaseModel):
    request_id: str
    enhanced_text: str
    tags: list[str] = Field(default_factory=list)
    provider: str
    model: str


class ExtractRequestSchema(BaseModel):
    text: str = Field(..., min_length=1, max_length=20_000)
    schema_hint: str | None = None
    mode: str = Field(default="auto")


class ExtractResponseSchema(BaseModel):
    request_id: str
    source: str
    provider: str
    model: str
    skills: list[str] = Field(default_factory=list)
    experience_years: int | None = None
    education: str | None = None
    industry: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)
    salary_text: str | None = None
    extras: dict = Field(default_factory=dict)


class ClassifyRequestSchema(BaseModel):
    text: str = Field(..., min_length=1, max_length=20_000)
    context: str | None = None
    mode: str = Field(default="auto")


class ClassifyResponseSchema(BaseModel):
    request_id: str
    text_preview: str
    risk_score: float
    primary_category: str
    categories: list[str]
    action: str
    reason: str
    provider: str
    model: str
    source: str
