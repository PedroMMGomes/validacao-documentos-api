import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.billing_record import BillingRecord

from app.modules.Billing.cost_config import CUSTO_POR_PROVIDER, DEFAULT_CUSTO

logger = get_logger(__name__)


async def record_billing(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    tokens_input: int,
    tokens_output: int,
    modelo: str,
    llm_provider: str | None = None,
    api_key_id: uuid.UUID | None = None,
) -> BillingRecord:
    custo_input, custo_output = CUSTO_POR_PROVIDER.get(
        (llm_provider or "").lower(), DEFAULT_CUSTO
    )
    custo_total = (tokens_input * custo_input) + (tokens_output * custo_output)

    record = BillingRecord(
        tenant_id=tenant_id,
        request_id=request_id,
        api_key_id=api_key_id,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        modelo=modelo,
        llm_provider=llm_provider,
        custo_unitario=custo_input,
        custo_total=custo_total,
    )
    db.add(record)
    await db.flush()

    logger.info(
        "record_billing | ok",
        extra={
            "tenant_id": str(tenant_id),
            "request_id": str(request_id),
            "api_key_id": str(api_key_id) if api_key_id else None,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "custo_total": custo_total,
            "modelo": modelo,
            "llm_provider": llm_provider,
        },
    )
    return record
