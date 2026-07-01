from datetime import datetime

from pydantic import BaseModel, Field


class BillingSummary(BaseModel):
    tenant_id: str
    total_requests: int
    total_tokens_input: int
    total_tokens_output: int
    estimated_cost_brl: float
    period_from: datetime
    period_to: datetime


# ── API Key schemas ──────────────────────────────────────────


class APIKeyCreate(BaseModel):
    tenant_id: str
    nome_cliente: str = Field(..., min_length=1, max_length=255)
    owner: str | None = Field(None, max_length=255)
    quota_diaria: int = Field(1000, ge=1)


class APIKeyCreated(BaseModel):
    id: str
    tenant_id: str
    nome_cliente: str
    owner: str | None
    quota_diaria: int
    status: str
    raw_key: str


class APIKeyRead(BaseModel):
    id: str
    tenant_id: str
    nome_cliente: str
    owner: str | None
    status: str
    quota_diaria: int
    key_prefix: str | None = None
    created_at: datetime


class APIKeyUpdate(BaseModel):
    nome_cliente: str | None = Field(None, min_length=1, max_length=255)
    owner: str | None = Field(None, max_length=255)
    quota_diaria: int | None = Field(None, ge=1)
    status: str | None = Field(None, pattern="^(active|revoked)$")


# ── Tenant schemas ───────────────────────────────────────────


class TenantCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    plano: str = Field("basico", max_length=100)
    email_contato: str = Field(..., min_length=1, max_length=255)


class TenantRead(BaseModel):
    id: str
    nome: str
    plano: str
    email_contato: str
    ativo: bool


class TenantUpdate(BaseModel):
    nome: str | None = Field(None, min_length=1, max_length=255)
    plano: str | None = Field(None, max_length=100)
    email_contato: str | None = Field(None, min_length=1, max_length=255)
    ativo: bool | None = None


# ── Usage schemas ────────────────────────────────────────────


class UsageByProvider(BaseModel):
    provider: str
    validacoes: int
    tokens_input: int
    tokens_output: int
    custo_total: float


class UsageByAPIKey(BaseModel):
    api_key_id: str | None
    nome_cliente: str
    owner: str | None
    validacoes: int
    tokens_input: int
    tokens_output: int
    custo_total: float


class UsageDetailRow(BaseModel):
    date: str
    request_id: str
    api_key_id: str | None
    nome_cliente: str
    owner: str | None
    llm_provider: str
    tokens_input: int
    tokens_output: int
    custo_total: float
    tenant_id: str


class UsageSummaryResponse(BaseModel):
    period_from: datetime
    period_to: datetime
    by_provider: list[UsageByProvider]
    by_api_key: list[UsageByAPIKey]


# ── Admin schemas ────────────────────────────────────────────


class UsageByTenant(BaseModel):
    tenant_id: str
    nome: str
    plano: str
    validacoes: int
    tokens_input: int
    tokens_output: int
    custo_total: float


class QuotaUsageRow(BaseModel):
    id: str
    nome_cliente: str
    owner: str | None
    quota_diaria: int
    usado_hoje: int
    pct_usado: float


class AdminBillingSummary(BaseModel):
    tenant_id: str
    total_requests: int
    total_tokens_input: int
    total_tokens_output: int
    estimated_cost_brl: float
    period_from: datetime
    period_to: datetime


class AdminUsageSummaryResponse(BaseModel):
    period_from: datetime
    period_to: datetime
    by_provider: list[UsageByProvider]
    by_api_key: list[UsageByAPIKey]
