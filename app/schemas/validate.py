from datetime import datetime

from pydantic import BaseModel, Field


class ProviderResult(BaseModel):
    tag: str
    ok: bool | None = None
    reason: str | None = None
    confidence: float | None = None
    tokens_used: dict | None = Field(default=None, description="{ input: int, output: int }")
    model_used: str | None = None
    error: str | None = None


class ValidateResponse(BaseModel):
    request_id: str
    status: str
    ok: bool | None = None
    reason: str | None = None
    confidence: float | None = None
    document_type: str | None = None
    regra: str | None = None
    processed_at: datetime | None = None
    tokens_used: dict | None = Field(default=None, description="{ input: int, output: int }")
    results: list[ProviderResult] | None = Field(default=None, description="Resultado individual por provedor LLM")
    artifacts_manifest_url: str | None = None


class ErrorResponse(BaseModel):
    request_id: str
    status: str = "error"
    error_code: str
    message: str
