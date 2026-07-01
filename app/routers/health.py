from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/metrics")
async def metrics():
    async with async_session() as db:
        try:
            await db.execute(text("SELECT 1"))
            db_status = "up"
        except Exception:
            db_status = "down"

    return {
        "database": db_status,
        "service": "validacao-documentos",
        "version": "1.0.0",
    }
