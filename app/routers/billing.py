import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database import get_db
from app.models.billing_record import BillingRecord
from app.modules import auth
from app.modules.Billing import usage_service
from app.schemas.billing import (
    BillingSummary,
    UsageDetailRow,
    UsageSummaryResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["billing"])


@router.get("/billing/summary", response_model=BillingSummary)
async def get_billing_summary(
    from_date: datetime = Query(..., alias="from"),
    to_date: datetime = Query(..., alias="to"),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    logger.info("get_billing_summary | inicio", extra={"from": str(from_date), "to": str(to_date)})

    tenant, _ = await auth.authenticate(db, x_api_key)

    stmt = (
        select(
            func.count(BillingRecord.id).label("total_requests"),
            func.coalesce(func.sum(BillingRecord.tokens_input), 0).label("total_tokens_input"),
            func.coalesce(func.sum(BillingRecord.tokens_output), 0).label("total_tokens_output"),
            func.coalesce(func.sum(BillingRecord.custo_total), 0.0).label("estimated_cost_brl"),
        )
        .where(
            BillingRecord.tenant_id == tenant.id,
            BillingRecord.created_at >= from_date,
            BillingRecord.created_at <= to_date,
        )
    )

    result = await db.execute(stmt)
    row = result.one()

    logger.info(
        "get_billing_summary | ok",
        extra={"tenant_id": str(tenant.id), "total_requests": row.total_requests},
    )

    return BillingSummary(
        tenant_id=str(tenant.id),
        total_requests=row.total_requests,
        total_tokens_input=row.total_tokens_input,
        total_tokens_output=row.total_tokens_output,
        estimated_cost_brl=round(row.estimated_cost_brl, 6),
        period_from=from_date,
        period_to=to_date,
    )


@router.get("/billing/usage", response_model=UsageSummaryResponse)
async def get_billing_usage(
    from_date: datetime = Query(..., alias="from"),
    to_date: datetime = Query(..., alias="to"),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    logger.info("get_billing_usage | inicio", extra={"from": str(from_date), "to": str(to_date)})

    tenant, _ = await auth.authenticate(db, x_api_key)

    by_provider = await usage_service.usage_by_provider(db, tenant.id, from_date, to_date)
    by_api_key = await usage_service.usage_by_api_key(db, tenant.id, from_date, to_date)

    logger.info(
        "get_billing_usage | ok",
        extra={"tenant_id": str(tenant.id), "providers": len(by_provider), "api_keys": len(by_api_key)},
    )

    return UsageSummaryResponse(
        period_from=from_date,
        period_to=to_date,
        by_provider=by_provider,
        by_api_key=by_api_key,
    )


@router.get("/billing/usage/detail", response_model=list[UsageDetailRow])
async def get_billing_usage_detail(
    from_date: datetime = Query(..., alias="from"),
    to_date: datetime = Query(..., alias="to"),
    api_key_id: str | None = Query(None, alias="api_key_id"),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    logger.info(
        "get_billing_usage_detail | inicio",
        extra={"from": str(from_date), "to": str(to_date), "api_key_id": api_key_id},
    )

    tenant, _ = await auth.authenticate(db, x_api_key)

    parsed_api_key_id: uuid.UUID | None = None
    if api_key_id:
        try:
            parsed_api_key_id = uuid.UUID(api_key_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="api_key_id invalido")

    try:
        rows = await usage_service.usage_detail(
            db=db,
            tenant_id=tenant.id,
            from_dt=from_date,
            to_dt=to_date,
            api_key_id=parsed_api_key_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(
        "get_billing_usage_detail | ok",
        extra={"tenant_id": str(tenant.id), "rows": len(rows)},
    )

    return rows
