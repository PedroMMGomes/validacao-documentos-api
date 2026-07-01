import secrets
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logging import get_logger
from app.database import get_db
from app.models.api_key import APIKey
from app.models.billing_record import BillingRecord
from app.models.tenant import Tenant
from app.models.validation_request import ValidationRequest
from app.modules.Billing import api_key_service, usage_service
from app.schemas.billing import (
    APIKeyCreate,
    APIKeyCreated,
    APIKeyRead,
    APIKeyUpdate,
    AdminBillingSummary,
    AdminUsageSummaryResponse,
    QuotaUsageRow,
    TenantCreate,
    TenantRead,
    TenantUpdate,
    UsageByTenant,
    UsageDetailRow,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/admin", tags=["admin"])


async def verify_admin_key(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    if not settings.ADMIN_API_KEY:
        logger.error("verify_admin_key | ADMIN_API_KEY nao configurada")
        raise HTTPException(
            status_code=503,
            detail={"error_code": "ADMIN_NOT_CONFIGURED", "message": "ADMIN_API_KEY not configured on server"},
        )
    if not secrets.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        logger.warning("verify_admin_key | chave invalida")
        raise HTTPException(
            status_code=401,
            detail={"error_code": "INVALID_ADMIN_KEY", "message": "Invalid admin key"},
        )
    return x_admin_key


# ── API Key CRUD ─────────────────────────────────────────────


@router.post("/api-keys", response_model=APIKeyCreated, status_code=201)
async def create_api_key(
    body: APIKeyCreate,
    _admin: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    logger.info("create_api_key | admin | inicio", extra={"tenant_id": body.tenant_id})

    try:
        tenant_id = uuid.UUID(body.tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="tenant_id invalido")

    api_key_obj, raw_key = await api_key_service.create_api_key(
        db=db,
        tenant_id=tenant_id,
        nome_cliente=body.nome_cliente,
        quota_diaria=body.quota_diaria,
        owner=body.owner,
    )
    await db.commit()

    return APIKeyCreated(
        id=str(api_key_obj.id),
        tenant_id=str(api_key_obj.tenant_id),
        nome_cliente=api_key_obj.nome_cliente,
        owner=api_key_obj.owner,
        quota_diaria=api_key_obj.quota_diaria,
        status=api_key_obj.status,
        raw_key=raw_key,
    )


@router.get("/api-keys", response_model=list[APIKeyRead])
async def list_api_keys(
    tenant_id: str = Query(..., alias="tenant_id"),
    _admin: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    logger.info("list_api_keys | admin | inicio", extra={"tenant_id": tenant_id})

    try:
        tid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="tenant_id invalido")

    keys = await api_key_service.list_api_keys(db=db, tenant_id=tid)

    return [
        APIKeyRead(
            id=str(k.id),
            tenant_id=str(k.tenant_id),
            nome_cliente=k.nome_cliente,
            owner=k.owner,
            status=k.status,
            quota_diaria=k.quota_diaria,
            key_prefix=k.key_prefix,
            created_at=k.created_at,
        )
        for k in keys
    ]


@router.patch("/api-keys/{key_id}", response_model=APIKeyRead)
async def update_api_key(
    key_id: str,
    body: APIKeyUpdate,
    _admin: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    logger.info("update_api_key | admin | inicio", extra={"key_id": key_id})

    try:
        kid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="key_id invalido")

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=422, detail="Nenhum campo para atualizar")

    updated = await api_key_service.update_api_key(
        db=db,
        key_id=kid,
        tenant_id=None,
        **update_data,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="API key nao encontrada")

    await db.commit()

    return APIKeyRead(
        id=str(updated.id),
        tenant_id=str(updated.tenant_id),
        nome_cliente=updated.nome_cliente,
        owner=updated.owner,
        status=updated.status,
        quota_diaria=updated.quota_diaria,
        key_prefix=updated.key_prefix,
        created_at=updated.created_at,
    )


@router.delete("/api-keys/{key_id}", status_code=204)
async def delete_api_key(
    key_id: str,
    tenant_id: str = Query(..., alias="tenant_id"),
    _admin: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    logger.info("delete_api_key | admin | inicio", extra={"key_id": key_id, "tenant_id": tenant_id})

    try:
        kid = uuid.UUID(key_id)
        tid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="key_id ou tenant_id invalido")

    deleted = await api_key_service.delete_api_key(db=db, key_id=kid, tenant_id=tid)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key nao encontrada")

    await db.commit()


# ── Tenant CRUD ──────────────────────────────────────────────


@router.get("/tenants", response_model=list[TenantRead])
async def list_tenants(
    _admin: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    logger.info("list_tenants | admin | inicio")

    stmt = select(Tenant).order_by(Tenant.nome)
    result = await db.execute(stmt)
    tenants = list(result.scalars().all())

    logger.info("list_tenants | ok", extra={"count": len(tenants)})

    return [
        TenantRead(
            id=str(t.id),
            nome=t.nome,
            plano=t.plano,
            email_contato=t.email_contato,
            ativo=t.ativo,
        )
        for t in tenants
    ]


@router.post("/tenants", response_model=TenantRead, status_code=201)
async def create_tenant(
    body: TenantCreate,
    _admin: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    logger.info("create_tenant | admin | inicio", extra={"nome": body.nome})

    tenant = Tenant(
        nome=body.nome,
        plano=body.plano,
        email_contato=body.email_contato,
        ativo=True,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    logger.info("create_tenant | ok", extra={"tenant_id": str(tenant.id)})

    return TenantRead(
        id=str(tenant.id),
        nome=tenant.nome,
        plano=tenant.plano,
        email_contato=tenant.email_contato,
        ativo=tenant.ativo,
    )


@router.patch("/tenants/{tenant_id}", response_model=TenantRead)
async def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    _admin: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    logger.info("update_tenant | admin | inicio", extra={"tenant_id": tenant_id})

    try:
        tid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="tenant_id invalido")

    stmt = select(Tenant).where(Tenant.id == tid)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=422, detail="Nenhum campo para atualizar")

    for field, value in update_data.items():
        setattr(tenant, field, value)

    await db.commit()
    await db.refresh(tenant)

    logger.info("update_tenant | ok", extra={"tenant_id": str(tenant.id)})

    return TenantRead(
        id=str(tenant.id),
        nome=tenant.nome,
        plano=tenant.plano,
        email_contato=tenant.email_contato,
        ativo=tenant.ativo,
    )


# ── Admin Billing ────────────────────────────────────────────


@router.get("/billing/summary", response_model=AdminBillingSummary)
async def admin_billing_summary(
    tenant_id: str = Query(..., alias="tenant_id"),
    from_date: datetime = Query(..., alias="from"),
    to_date: datetime = Query(..., alias="to"),
    _admin: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    logger.info("admin_billing_summary | inicio", extra={"tenant_id": tenant_id, "from": str(from_date), "to": str(to_date)})

    try:
        tid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="tenant_id invalido")

    stmt = (
        select(
            func.count(BillingRecord.id).label("total_requests"),
            func.coalesce(func.sum(BillingRecord.tokens_input), 0).label("total_tokens_input"),
            func.coalesce(func.sum(BillingRecord.tokens_output), 0).label("total_tokens_output"),
            func.coalesce(func.sum(BillingRecord.custo_total), 0.0).label("estimated_cost_brl"),
        )
        .where(
            BillingRecord.tenant_id == tid,
            BillingRecord.created_at >= from_date,
            BillingRecord.created_at <= to_date,
        )
    )

    result = await db.execute(stmt)
    row = result.one()

    logger.info("admin_billing_summary | ok", extra={"tenant_id": tenant_id, "total_requests": row.total_requests})

    return AdminBillingSummary(
        tenant_id=tenant_id,
        total_requests=row.total_requests,
        total_tokens_input=row.total_tokens_input,
        total_tokens_output=row.total_tokens_output,
        estimated_cost_brl=round(row.estimated_cost_brl, 6),
        period_from=from_date,
        period_to=to_date,
    )


@router.get("/billing/usage", response_model=AdminUsageSummaryResponse)
async def admin_billing_usage(
    tenant_id: str = Query(..., alias="tenant_id"),
    from_date: datetime = Query(..., alias="from"),
    to_date: datetime = Query(..., alias="to"),
    _admin: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    logger.info("admin_billing_usage | inicio", extra={"tenant_id": tenant_id})

    try:
        tid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="tenant_id invalido")

    by_provider = await usage_service.usage_by_provider(db, tid, from_date, to_date)
    by_api_key = await usage_service.usage_by_api_key(db, tid, from_date, to_date)

    logger.info("admin_billing_usage | ok", extra={"tenant_id": tenant_id})

    return AdminUsageSummaryResponse(
        period_from=from_date,
        period_to=to_date,
        by_provider=by_provider,
        by_api_key=by_api_key,
    )


@router.get("/billing/usage/detail", response_model=list[UsageDetailRow])
async def admin_billing_usage_detail(
    tenant_id: str = Query(..., alias="tenant_id"),
    from_date: datetime = Query(..., alias="from"),
    to_date: datetime = Query(..., alias="to"),
    api_key_id: str | None = Query(None, alias="api_key_id"),
    _admin: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    logger.info("admin_billing_usage_detail | inicio", extra={"tenant_id": tenant_id})

    try:
        tid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="tenant_id invalido")

    parsed_api_key_id: uuid.UUID | None = None
    if api_key_id:
        try:
            parsed_api_key_id = uuid.UUID(api_key_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="api_key_id invalido")

    try:
        rows = await usage_service.usage_detail(
            db=db,
            tenant_id=tid,
            from_dt=from_date,
            to_dt=to_date,
            api_key_id=parsed_api_key_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info("admin_billing_usage_detail | ok", extra={"tenant_id": tenant_id, "rows": len(rows)})

    return rows


@router.get("/billing/usage/all-tenants", response_model=list[UsageByTenant])
async def admin_billing_all_tenants(
    from_date: datetime = Query(..., alias="from"),
    to_date: datetime = Query(..., alias="to"),
    _admin: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    logger.info("admin_billing_all_tenants | inicio", extra={"from": str(from_date), "to": str(to_date)})

    rows = await usage_service.usage_all_tenants(db, from_date, to_date)

    logger.info("admin_billing_all_tenants | ok", extra={"tenants": len(rows)})

    return rows


@router.get("/api-keys/quota-usage", response_model=list[QuotaUsageRow])
async def admin_quota_usage(
    tenant_id: str = Query(..., alias="tenant_id"),
    _admin: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    logger.info("admin_quota_usage | inicio", extra={"tenant_id": tenant_id})

    try:
        tid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="tenant_id invalido")

    today = date.today()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())

    keys_stmt = select(APIKey).where(APIKey.tenant_id == tid).order_by(APIKey.nome_cliente)
    keys_result = await db.execute(keys_stmt)
    keys = list(keys_result.scalars().all())

    rows = []
    for key in keys:
        count_stmt = select(func.count()).select_from(ValidationRequest).where(
            ValidationRequest.api_key_id == key.id,
            ValidationRequest.created_at >= start_of_day,
            ValidationRequest.created_at <= end_of_day,
        )
        count_result = await db.execute(count_stmt)
        usado_hoje = count_result.scalar() or 0

        pct_usado = round((usado_hoje / key.quota_diaria) * 100, 1) if key.quota_diaria > 0 else 0.0

        rows.append(QuotaUsageRow(
            id=str(key.id),
            nome_cliente=key.nome_cliente,
            owner=key.owner,
            quota_diaria=key.quota_diaria,
            usado_hoje=usado_hoje,
            pct_usado=pct_usado,
        ))

    logger.info("admin_quota_usage | ok", extra={"tenant_id": tenant_id, "keys": len(rows)})

    return rows
