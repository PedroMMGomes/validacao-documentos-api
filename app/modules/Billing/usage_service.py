import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.api_key import APIKey
from app.models.billing_record import BillingRecord
from app.models.tenant import Tenant

logger = get_logger(__name__)

MAX_DETAIL_ROWS = 50_000


async def usage_by_provider(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
) -> list[dict]:
    logger.info(
        "usage_by_provider | inicio",
        extra={"tenant_id": str(tenant_id), "from": str(from_dt), "to": str(to_dt)},
    )

    stmt = (
        select(
            func.coalesce(BillingRecord.llm_provider, "(sem dados)").label("provider"),
            func.count(BillingRecord.id).label("total_records"),
            func.count(func.distinct(BillingRecord.request_id)).label("validacoes"),
            func.coalesce(func.sum(BillingRecord.tokens_input), 0).label("tokens_input"),
            func.coalesce(func.sum(BillingRecord.tokens_output), 0).label("tokens_output"),
            func.coalesce(func.sum(BillingRecord.custo_total), 0.0).label("custo_total"),
        )
        .where(
            BillingRecord.tenant_id == tenant_id,
            BillingRecord.created_at >= from_dt,
            BillingRecord.created_at <= to_dt,
        )
        .group_by(BillingRecord.llm_provider)
    )
    result = await db.execute(stmt)
    rows = [
        {
            "provider": row.provider,
            "validacoes": row.validacoes,
            "tokens_input": int(row.tokens_input),
            "tokens_output": int(row.tokens_output),
            "custo_total": float(row.custo_total),
        }
        for row in result.all()
    ]

    logger.info(
        "usage_by_provider | ok",
        extra={"tenant_id": str(tenant_id), "providers": len(rows)},
    )
    return rows


async def usage_by_api_key(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
) -> list[dict]:
    logger.info(
        "usage_by_api_key | inicio",
        extra={"tenant_id": str(tenant_id), "from": str(from_dt), "to": str(to_dt)},
    )

    stmt = (
        select(
            BillingRecord.api_key_id,
            APIKey.nome_cliente,
            APIKey.owner,
            func.count(BillingRecord.id).label("total_records"),
            func.count(func.distinct(BillingRecord.request_id)).label("validacoes"),
            func.coalesce(func.sum(BillingRecord.tokens_input), 0).label("tokens_input"),
            func.coalesce(func.sum(BillingRecord.tokens_output), 0).label("tokens_output"),
            func.coalesce(func.sum(BillingRecord.custo_total), 0.0).label("custo_total"),
        )
        .join(APIKey, BillingRecord.api_key_id == APIKey.id, isouter=True)
        .where(
            BillingRecord.tenant_id == tenant_id,
            BillingRecord.created_at >= from_dt,
            BillingRecord.created_at <= to_dt,
        )
        .group_by(BillingRecord.api_key_id, APIKey.nome_cliente, APIKey.owner)
    )
    result = await db.execute(stmt)
    rows = [
        {
            "api_key_id": str(row.api_key_id) if row.api_key_id else None,
            "nome_cliente": row.nome_cliente or "(sem dados)",
            "owner": row.owner,
            "validacoes": row.validacoes,
            "tokens_input": int(row.tokens_input),
            "tokens_output": int(row.tokens_output),
            "custo_total": float(row.custo_total),
        }
        for row in result.all()
    ]

    logger.info(
        "usage_by_api_key | ok",
        extra={"tenant_id": str(tenant_id), "api_keys": len(rows)},
    )
    return rows


async def usage_detail(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
    api_key_id: uuid.UUID | None = None,
    limit: int = MAX_DETAIL_ROWS,
) -> list[dict]:
    logger.info(
        "usage_detail | inicio",
        extra={
            "tenant_id": str(tenant_id),
            "from": str(from_dt),
            "to": str(to_dt),
            "api_key_id": str(api_key_id) if api_key_id else None,
            "limit": limit,
        },
    )

    count_stmt = select(func.count(BillingRecord.id)).where(
        BillingRecord.tenant_id == tenant_id,
        BillingRecord.created_at >= from_dt,
        BillingRecord.created_at <= to_dt,
    )
    if api_key_id:
        count_stmt = count_stmt.where(BillingRecord.api_key_id == api_key_id)

    count_result = await db.execute(count_stmt)
    total_rows = count_result.scalar() or 0

    if total_rows > MAX_DETAIL_ROWS:
        logger.warning(
            "usage_detail | limite_excedido",
            extra={"total_rows": total_rows, "max": MAX_DETAIL_ROWS},
        )
        raise ValueError(
            f"Periodo gera {total_rows} registros, maximo permitido e {MAX_DETAIL_ROWS}. "
            "Reduza o intervalo de datas."
        )

    stmt = (
        select(
            BillingRecord.created_at.label("date"),
            BillingRecord.request_id,
            BillingRecord.api_key_id,
            APIKey.nome_cliente,
            APIKey.owner,
            BillingRecord.llm_provider,
            BillingRecord.tokens_input,
            BillingRecord.tokens_output,
            BillingRecord.custo_total,
            BillingRecord.tenant_id,
        )
        .join(APIKey, BillingRecord.api_key_id == APIKey.id, isouter=True)
        .where(
            BillingRecord.tenant_id == tenant_id,
            BillingRecord.created_at >= from_dt,
            BillingRecord.created_at <= to_dt,
        )
        .order_by(BillingRecord.created_at.asc())
    )
    if api_key_id:
        stmt = stmt.where(BillingRecord.api_key_id == api_key_id)

    result = await db.execute(stmt)
    rows = [
        {
            "date": row.date.isoformat() if row.date else None,
            "request_id": str(row.request_id),
            "api_key_id": str(row.api_key_id) if row.api_key_id else None,
            "nome_cliente": row.nome_cliente or "(sem dados)",
            "owner": row.owner,
            "llm_provider": row.llm_provider or "(sem dados)",
            "tokens_input": int(row.tokens_input),
            "tokens_output": int(row.tokens_output),
            "custo_total": float(row.custo_total),
            "tenant_id": str(row.tenant_id),
        }
        for row in result.all()
    ]

    logger.info(
        "usage_detail | ok",
        extra={"tenant_id": str(tenant_id), "rows": len(rows)},
    )
    return rows


async def usage_all_tenants(
    db: AsyncSession,
    from_dt: datetime,
    to_dt: datetime,
) -> list[dict]:
    logger.info(
        "usage_all_tenants | inicio",
        extra={"from": str(from_dt), "to": str(to_dt)},
    )

    stmt = (
        select(
            Tenant.id.label("tenant_id"),
            Tenant.nome,
            Tenant.plano,
            func.count(func.distinct(BillingRecord.request_id)).label("validacoes"),
            func.coalesce(func.sum(BillingRecord.tokens_input), 0).label("tokens_input"),
            func.coalesce(func.sum(BillingRecord.tokens_output), 0).label("tokens_output"),
            func.coalesce(func.sum(BillingRecord.custo_total), 0.0).label("custo_total"),
        )
        .join(BillingRecord, BillingRecord.tenant_id == Tenant.id)
        .where(
            BillingRecord.created_at >= from_dt,
            BillingRecord.created_at <= to_dt,
        )
        .group_by(Tenant.id, Tenant.nome, Tenant.plano)
    )
    result = await db.execute(stmt)
    rows = [
        {
            "tenant_id": str(row.tenant_id),
            "nome": row.nome,
            "plano": row.plano,
            "validacoes": int(row.validacoes),
            "tokens_input": int(row.tokens_input),
            "tokens_output": int(row.tokens_output),
            "custo_total": float(row.custo_total),
        }
        for row in result.all()
    ]

    logger.info(
        "usage_all_tenants | ok",
        extra={"tenants": len(rows)},
    )
    return rows
