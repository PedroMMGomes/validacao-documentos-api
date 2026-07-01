import asyncio
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logging import get_logger
from app.database import get_db
from app.modules import auth, request_repo
from app.schemas.request import RequestResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["requests"])


@router.get("/requests/{request_id}", response_model=RequestResponse)
async def get_request(
    request_id: uuid.UUID,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    logger.info("get_request | inicio", extra={"request_id": str(request_id)})

    tenant, _ = await auth.authenticate(db, x_api_key)

    req = await request_repo.get_by_id(db, request_id, tenant.id)
    if req is None:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "Requisicao nao encontrada"})

    return RequestResponse(
        request_id=str(req.id),
        status="ok" if req.status == "DONE" and req.resultado_ok else ("rejected" if req.status == "DONE" else req.status.lower()),
        ok=req.resultado_ok,
        reason=req.resultado_reason,
        confidence=req.resultado_confidence,
        document_type=req.document_type,
        processed_at=req.updated_at,
        tokens_used={"input": req.tokens_input, "output": req.tokens_output} if req.tokens_input else None,
    )


@router.get("/requests/{request_id}/artifacts/manifest")
async def get_artifacts_manifest(
    request_id: uuid.UUID,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    logger.info("get_artifacts_manifest | inicio", extra={"request_id": str(request_id)})

    tenant, api_key_obj = await auth.authenticate(db, x_api_key)

    req = await request_repo.get_by_id(db, request_id, tenant.id)
    if req is None:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "Requisicao nao encontrada"})

    if not settings.REQUEST_ARTIFACTS_PATH:
        raise HTTPException(status_code=404, detail={"error_code": "ARTIFACTS_DISABLED", "message": "Artifacts nao configurados"})

    manifest_path = Path(settings.REQUEST_ARTIFACTS_PATH) / str(api_key_obj.id) / str(request_id) / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail={"error_code": "ARTIFACTS_NOT_FOUND", "message": "Manifesto nao encontrado"})

    def _read_manifest() -> dict:
        return json.loads(manifest_path.read_bytes())

    data = await asyncio.to_thread(_read_manifest)

    logger.info("get_artifacts_manifest | ok", extra={"request_id": str(request_id)})
    return JSONResponse(content=data)
