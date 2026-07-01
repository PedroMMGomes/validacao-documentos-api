"""Seed script — cria tenant e API key de teste."""
import asyncio
import hashlib
import uuid

from app.database import async_session
from app.models.api_key import APIKey
from app.models.tenant import Tenant

TENANT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
API_KEY_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
RAW_API_KEY = "vd_test_12345678"


async def seed():
    async with async_session() as db:
        existing_tenant = await db.get(Tenant, TENANT_ID)
        if existing_tenant:
            print(f"Tenant ja existe: {TENANT_ID}")
            return

        tenant = Tenant(
            id=TENANT_ID,
            nome="Operadora Teste",
            plano="basico",
            email_contato="teste@operadora.com",
            ativo=True,
        )
        db.add(tenant)
        await db.flush()

        key_hash = hashlib.sha256(RAW_API_KEY.encode()).hexdigest()
        api_key = APIKey(
            id=API_KEY_ID,
            tenant_id=TENANT_ID,
            key_hash=key_hash,
            nome_cliente="Cliente Teste",
            status="active",
            quota_diaria=1000,
        )
        db.add(api_key)

        await db.commit()
        print(f"Tenant criado: {TENANT_ID}")
        print(f"API Key criada: {API_KEY_ID}")
        print(f"Use esta API Key nos testes: {RAW_API_KEY}")


asyncio.run(seed())
