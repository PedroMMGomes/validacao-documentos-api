import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.api_key import APIKey

logger = get_logger(__name__)


def _hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def create_api_key(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    nome_cliente: str,
    quota_diaria: int = 1000,
    owner: str | None = None,
) -> tuple[APIKey, str]:
    raw_key = uuid.uuid4().hex
    key_hash = _hash_api_key(raw_key)
    key_prefix = raw_key[:8]

    api_key = APIKey(
        tenant_id=tenant_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        nome_cliente=nome_cliente,
        owner=owner,
        status="active",
        quota_diaria=quota_diaria,
    )
    db.add(api_key)
    await db.flush()

    logger.info(
        "create_api_key | ok",
        extra={
            "tenant_id": str(tenant_id),
            "api_key_id": str(api_key.id),
            "nome_cliente": nome_cliente,
            "owner": owner,
        },
    )
    return api_key, raw_key


async def list_api_keys(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[APIKey]:
    logger.info("list_api_keys | inicio", extra={"tenant_id": str(tenant_id)})

    stmt = (
        select(APIKey)
        .where(APIKey.tenant_id == tenant_id)
        .order_by(APIKey.created_at.desc())
    )
    result = await db.execute(stmt)
    keys = list(result.scalars().all())

    logger.info(
        "list_api_keys | ok",
        extra={"tenant_id": str(tenant_id), "count": len(keys)},
    )
    return keys


async def update_api_key(
    db: AsyncSession,
    key_id: uuid.UUID,
    tenant_id: uuid.UUID | None = None,
    nome_cliente: str | None = None,
    owner: str | None = None,
    quota_diaria: int | None = None,
    status: str | None = None,
) -> APIKey | None:
    logger.info(
        "update_api_key | inicio",
        extra={"key_id": str(key_id), "tenant_id": str(tenant_id) if tenant_id else "admin"},
    )

    conditions = [APIKey.id == key_id]
    if tenant_id is not None:
        conditions.append(APIKey.tenant_id == tenant_id)

    stmt = select(APIKey).where(*conditions)
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if api_key is None:
        logger.warning(
            "update_api_key | nao_encontrada",
            extra={"key_id": str(key_id), "tenant_id": str(tenant_id) if tenant_id else "admin"},
        )
        return None

    if nome_cliente is not None:
        api_key.nome_cliente = nome_cliente
    if owner is not None:
        api_key.owner = owner
    if quota_diaria is not None:
        api_key.quota_diaria = quota_diaria
    if status is not None:
        api_key.status = status

    await db.flush()

    logger.info(
        "update_api_key | ok",
        extra={"key_id": str(key_id), "tenant_id": str(tenant_id) if tenant_id else "admin"},
    )
    return api_key


async def delete_api_key(
    db: AsyncSession,
    key_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> bool:
    logger.info(
        "delete_api_key | inicio",
        extra={"key_id": str(key_id), "tenant_id": str(tenant_id)},
    )

    stmt = select(APIKey).where(
        APIKey.id == key_id,
        APIKey.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if api_key is None:
        logger.warning(
            "delete_api_key | nao_encontrada",
            extra={"key_id": str(key_id), "tenant_id": str(tenant_id)},
        )
        return False

    api_key.status = "revoked"
    await db.flush()

    logger.info(
        "delete_api_key | ok",
        extra={"key_id": str(key_id), "tenant_id": str(tenant_id)},
    )
    return True
