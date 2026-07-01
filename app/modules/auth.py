import hashlib
import uuid
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidAPIKeyError, QuotaExceededError
from app.core.logging import get_logger
from app.models.api_key import APIKey
from app.models.tenant import Tenant
from app.models.validation_request import ValidationRequest

logger = get_logger(__name__)


def _hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def authenticate(db: AsyncSession, raw_api_key: str) -> tuple[Tenant, APIKey]:
    logger.info("authenticate | inicio", extra={"key_prefix": raw_api_key[:8] + "..."})

    key_hash = _hash_api_key(raw_api_key)
    stmt = select(APIKey).where(APIKey.key_hash == key_hash, APIKey.status == "active")
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if api_key is None:
        logger.warning("authenticate | api_key_nao_encontrada", extra={"key_hash": key_hash[:16]})
        raise InvalidAPIKeyError()

    tenant_stmt = select(Tenant).where(Tenant.id == api_key.tenant_id, Tenant.ativo.is_(True))
    tenant_result = await db.execute(tenant_stmt)
    tenant = tenant_result.scalar_one_or_none()

    if tenant is None:
        logger.error("authenticate | tenant_nao_encontrado_ou_inativo", extra={"tenant_id": str(api_key.tenant_id)})
        raise InvalidAPIKeyError("Tenant inactive or not found")

    await _check_quota(db, api_key)

    logger.info("authenticate | ok", extra={"tenant_id": str(tenant.id), "api_key_id": str(api_key.id)})
    return tenant, api_key


async def _check_quota(db: AsyncSession, api_key: APIKey) -> None:
    today = date.today()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())

    stmt = select(func.count()).select_from(ValidationRequest).where(
        ValidationRequest.api_key_id == api_key.id,
        ValidationRequest.created_at >= start_of_day,
        ValidationRequest.created_at <= end_of_day,
    )
    result = await db.execute(stmt)
    count_today = result.scalar() or 0

    if count_today >= api_key.quota_diaria:
        logger.warning(
            "authenticate | quota_excedida",
            extra={"api_key_id": str(api_key.id), "count_today": count_today, "quota": api_key.quota_diaria},
        )
        raise QuotaExceededError()

    logger.info("authenticate | quota_ok", extra={"count_today": count_today, "quota": api_key.quota_diaria})


def resolve_tenant_folder(tenant_id: uuid.UUID) -> str:
    return str(tenant_id)
