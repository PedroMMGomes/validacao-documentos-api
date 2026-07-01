import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import LLMError
from app.core.logging import get_logger
from app.models.api_key import APIKey
from app.models.tenant import Tenant
from app.models.validation_request import ValidationRequest

logger = get_logger(__name__)


async def create_request(
    db: AsyncSession,
    tenant: Tenant,
    api_key: APIKey,
    arquivo_path: str,
    document_type: str | None = None,
    regra: str | None = None,
) -> ValidationRequest:
    req = ValidationRequest(
        tenant_id=tenant.id,
        api_key_id=api_key.id,
        arquivo_path=arquivo_path,
        document_type=document_type,
        regra=regra,
        status="PENDING",
    )
    db.add(req)
    await db.flush()
    logger.info("create_request | ok", extra={"request_id": str(req.id), "status": req.status})
    return req


async def get_by_id(db: AsyncSession, request_id: uuid.UUID, tenant_id: uuid.UUID) -> ValidationRequest | None:
    stmt = select(ValidationRequest).where(
        ValidationRequest.id == request_id,
        ValidationRequest.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_status_done(
    db: AsyncSession,
    request_id: uuid.UUID,
    ok: bool,
    reason: str,
    confidence: float,
    llm_model: str,
    tokens_input: int,
    tokens_output: int,
    custo_estimado: float,
    llm_results: list[dict] | None = None,
) -> ValidationRequest:
    req = await db.get(ValidationRequest, request_id)
    if req is None:
        logger.error("update_status_done | request_nao_encontrada", extra={"request_id": str(request_id)})
        raise LLMError("Request not found for update")

    req.status = "DONE"
    req.resultado_ok = ok
    req.resultado_reason = reason
    req.resultado_confidence = confidence
    req.llm_model = llm_model
    req.tokens_input = tokens_input
    req.tokens_output = tokens_output
    req.custo_estimado = custo_estimado
    req.llm_results = llm_results
    req.updated_at = datetime.utcnow()

    await db.flush()
    logger.info(
        "update_status_done | ok",
        extra={"request_id": str(request_id), "ok": ok, "confidence": confidence, "providers": llm_model},
    )
    return req


async def update_status_error(db: AsyncSession, request_id: uuid.UUID, error_message: str) -> ValidationRequest:
    req = await db.get(ValidationRequest, request_id)
    if req is None:
        raise LLMError("Request not found for error update")

    req.status = "ERROR"
    req.resultado_reason = error_message
    req.updated_at = datetime.utcnow()

    await db.flush()
    logger.error("update_status_error | ok", extra={"request_id": str(request_id), "error": error_message})
    return req
