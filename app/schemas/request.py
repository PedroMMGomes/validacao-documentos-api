from datetime import datetime

from pydantic import BaseModel


class RequestResponse(BaseModel):
    request_id: str
    status: str
    ok: bool | None = None
    reason: str | None = None
    confidence: float | None = None
    document_type: str | None = None
    processed_at: datetime | None = None
    tokens_used: dict | None = None
