import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import LLMError
from app.core.logging import get_logger
from app.database import get_db
from app.modules import artifacts, auth, normalizer, request_repo, storage
from app.modules.Billing.cost_config import CUSTO_POR_PROVIDER, DEFAULT_CUSTO
from app.modules.Billing.record import record_billing
from app.modules.llm.base import LLMResponse
from app.modules.llm.factory import available_providers, get_llm_provider
from app.schemas.validate import ErrorResponse, ProviderResult, ValidateResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["validate"])

DOCUMENT_TYPES = {"guia_internacao", "laudo_medico", "receita", "pedido_exame", "outros"}

_VALID_TAGS = set(available_providers())

_MAX_CONCURRENT = getattr(settings, "MAX_CONCURRENT_REQUESTS", 200) or 200
_concurrency_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)


def _resolve_tags(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return []
    tags = [t.strip().lower() for t in raw.split(",") if t.strip()]
    deduped = list(dict.fromkeys(tags))
    invalid = [t for t in deduped if t not in _VALID_TAGS]
    if invalid:
        raise LLMError(f"Unknown LLM provider tags: {invalid}. Available: {sorted(_VALID_TAGS)}")
    return deduped


@router.post(
    "/validate",
    response_model=ValidateResponse,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def validate_document(
    file: UploadFile = File(...),
    document_type: str | None = Form(None),
    metadata: str | None = Form(None),
    regra: str | None = Form(None),
    llm_providers: str | None = Form(None),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    async with _concurrency_semaphore:
        return await _validate_document_inner(
            file=file,
            document_type=document_type,
            metadata=metadata,
            regra=regra,
            llm_providers=llm_providers,
            x_api_key=x_api_key,
            db=db,
        )


async def _validate_document_inner(
    file: UploadFile,
    document_type: str | None,
    metadata: str | None,
    regra: str | None,
    llm_providers: str | None,
    x_api_key: str,
    db: AsyncSession,
):
    request_id = uuid.uuid4()
    artifact_dir: Path | None = None
    logger.info("validate_document | inicio", extra={"request_id": str(request_id), "filename": file.filename})

    if document_type and document_type not in DOCUMENT_TYPES:
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                request_id=str(request_id),
                error_code="UNSUPPORTED_FORMAT",
                message=f"document_type invalido. Use: {', '.join(sorted(DOCUMENT_TYPES))}",
            ).model_dump(),
        )

    try:
        tags = _resolve_tags(llm_providers)
        tenant, api_key_obj = await auth.authenticate(db, x_api_key)

        file_content = await file.read()
        storage_uuid = request_id
        relative_path = await storage.save_file(tenant.id, storage_uuid, file.filename, file_content)

        req = await request_repo.create_request(db, tenant, api_key_obj, relative_path, document_type, regra=regra)
        request_id = req.id

        # [1] init artifacts dir + meta
        artifact_dir = await artifacts.init_artifact_dir(api_key_obj.id, req.id)
        await artifacts.write_meta(
            artifact_dir,
            request_id=req.id,
            api_key_id=api_key_obj.id,
            tenant_id=tenant.id,
            filename_original=file.filename or "unknown",
            document_type=document_type,
            regra_len=len(regra or ""),
            llm_providers=[t if t else settings.LLM_PROVIDER for t in tags] if tags else [settings.LLM_PROVIDER],
            file_content=file_content,
            storage_path_uuid=storage_uuid if storage_uuid != req.id else None,
        )
        # [2] original
        await artifacts.write_original(artifact_dir, file_content, file.filename or "unknown")

        normalized = await normalizer.normalize(file_content, file.filename)

        # [3] normalized
        await artifacts.write_normalized(artifact_dir, normalized.pages, normalized.ocr_text)

        if not tags:
            tags = [None]

        resolved_llm_tags = [t if t else settings.LLM_PROVIDER for t in tags]
        logger.info(
            "validate_document | antes_llm",
            extra={
                "request_id": str(req.id),
                "filename": file.filename,
                "file_bytes": len(file_content),
                "pages": len(normalized.pages),
                "page_dimensions": normalized.page_dimensions,
                "approx_rgb_bytes": normalized.approx_rgb_bytes,
                "jpeg_payload_bytes": normalized.jpeg_payload_bytes,
                "llm_providers_form": llm_providers or "",
                "llm_tags": ",".join(resolved_llm_tags),
                "regra_len": len(regra or ""),
                "document_type": document_type or "",
            },
        )

        coros = [_safe_validate(tag, normalized.pages, regra, normalized.ocr_text) for tag in tags]

        outcomes: list[_ValidateOutcome] = await asyncio.gather(*coros)

        all_errored = all(o.error is not None for o in outcomes)
        if all_errored:
            error_details = "; ".join(f"{o.tag}: {o.error}" for o in outcomes)
            logger.error("validate_document | all_providers_failed", extra={"request_id": str(request_id), "errors": error_details})

            # [4] error + provider errors
            for outcome in outcomes:
                await artifacts.write_provider(artifact_dir, outcome.tag, {"tag": outcome.tag, "error": outcome.error})
            await artifacts.write_error(artifact_dir, {"error_code": "ALL_PROVIDERS_FAILED", "details": error_details})
            await artifacts.finalize_manifest(artifact_dir, api_key_id=api_key_obj.id, request_id=req.id, complete=False)

            try:
                await request_repo.update_status_error(db, req.id, error_details)
                await db.commit()
            except Exception:
                await db.rollback()
            return JSONResponse(
                status_code=502,
                content=ErrorResponse(
                    request_id=str(request_id),
                    error_code="LLM_ERROR",
                    message=f"All LLM providers failed: {error_details}",
                ).model_dump(),
            )

        results: list[ProviderResult] = []
        total_input = 0
        total_output = 0
        all_ok = True
        primary_reason = ""
        primary_confidence = 0.0

        for outcome in outcomes:
            if outcome.error:
                results.append(ProviderResult(tag=outcome.tag, ok=None, error=outcome.error))
                all_ok = False
                await artifacts.write_provider(artifact_dir, outcome.tag, {"tag": outcome.tag, "error": outcome.error})
                continue

            r = outcome.result
            results.append(
                ProviderResult(
                    tag=outcome.tag,
                    ok=r.ok,
                    reason=r.reason,
                    confidence=r.confidence,
                    tokens_used={"input": r.tokens_input, "output": r.tokens_output},
                    model_used=r.model_used,
                )
            )
            # [4] provider result
            await artifacts.write_provider(
                artifact_dir,
                outcome.tag,
                {
                    "tag": outcome.tag,
                    "ok": r.ok,
                    "reason": r.reason,
                    "confidence": r.confidence,
                    "tokens_input": r.tokens_input,
                    "tokens_output": r.tokens_output,
                    "model_used": r.model_used,
                },
            )
            total_input += r.tokens_input
            total_output += r.tokens_output
            if not r.ok:
                all_ok = False

            try:
                await record_billing(
                    db=db,
                    tenant_id=tenant.id,
                    request_id=req.id,
                    tokens_input=r.tokens_input,
                    tokens_output=r.tokens_output,
                    modelo=r.model_used,
                    llm_provider=outcome.tag,
                    api_key_id=api_key_obj.id,
                )
            except Exception as billing_err:
                logger.error("validate_document | billing_error", extra={"tag": outcome.tag, "error": str(billing_err)})

        if results and results[0].ok is not None:
            primary_reason = results[0].reason or ""
            primary_confidence = results[0].confidence or 0.0

        custo_estimado = 0.0
        for outcome in outcomes:
            if not outcome.error and outcome.result:
                custo_in, custo_out = CUSTO_POR_PROVIDER.get(
                    outcome.tag.lower(), DEFAULT_CUSTO
                )
                custo_estimado += (
                    outcome.result.tokens_input * custo_in
                    + outcome.result.tokens_output * custo_out
                )
        results_data = [r.model_dump(exclude_none=True) for r in results]
        await request_repo.update_status_done(
            db=db,
            request_id=req.id,
            ok=all_ok,
            reason=primary_reason,
            confidence=primary_confidence,
            llm_model=",".join(o.tag for o in outcomes if not o.error),
            tokens_input=total_input,
            tokens_output=total_output,
            custo_estimado=custo_estimado,
            llm_results=results_data if len(results_data) > 1 else None,
        )

        await db.commit()

        single_mode = len(results) == 1 and results[0].error is None

        response = ValidateResponse(
            request_id=str(req.id),
            status="ok" if all_ok else "rejected",
            ok=all_ok if not single_mode else results[0].ok,
            reason=primary_reason,
            confidence=primary_confidence,
            document_type=document_type,
            regra=regra,
            tokens_used={"input": total_input, "output": total_output},
            results=results if not single_mode or len(tags) > 1 else None,
            artifacts_manifest_url=(
                f"{settings.PUBLIC_BASE_URL}/v1/requests/{req.id}/artifacts/manifest"
                if settings.REQUEST_ARTIFACTS_PATH
                else None
            ),
        )

        # [5] response + manifest
        await artifacts.write_response(artifact_dir, response.model_dump(mode="json"))
        await artifacts.finalize_manifest(artifact_dir, api_key_id=api_key_obj.id, request_id=req.id, complete=True)

        return response

    except HTTPException:
        raise
    except LLMError as e:
        await db.rollback()
        logger.error("validate_document | llm_error", extra={"request_id": str(request_id), "error": str(e)})
        await _write_artifact_error(artifact_dir, request_id, e, "LLM_ERROR")
        return JSONResponse(
            status_code=e.status_code,
            content=ErrorResponse(
                request_id=str(request_id),
                error_code="LLM_ERROR",
                message=str(e),
            ).model_dump(),
        )
    except Exception as e:
        await db.rollback()
        logger.error("validate_document | erro_nao_tratado", extra={"request_id": str(request_id), "error": str(e)})
        await _write_artifact_error(artifact_dir, request_id, e, "INTERNAL_ERROR")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                request_id=str(request_id),
                error_code="INTERNAL_ERROR",
                message="Erro interno do servidor",
            ).model_dump(),
        )


async def _write_artifact_error(
    artifact_dir: Path | None,
    request_id: uuid.UUID,
    exc: Exception,
    error_code: str,
) -> None:
    try:
        await artifacts.write_error(artifact_dir, {"error_code": error_code, "message": str(exc)})
        await artifacts.finalize_manifest(
            artifact_dir,
            api_key_id=uuid.UUID(int=0),
            request_id=request_id,
            complete=False,
        )
    except Exception:
        logger.warning("_write_artifact_error | falhou", extra={"request_id": str(request_id)})


class _ValidateOutcome:
    __slots__ = ("tag", "result", "error")

    def __init__(self, tag: str, result: LLMResponse | None, error: str | None):
        self.tag = tag
        self.result = result
        self.error = error


async def _safe_validate(tag: str | None, pages, regra, ocr_text) -> _ValidateOutcome:
    label = tag or "default"
    try:
        provider = get_llm_provider(tag)
        result = await provider.validate(pages=pages, regra=regra, ocr_text=ocr_text)
        return _ValidateOutcome(tag=label, result=result, error=None)
    except Exception as e:
        logger.error("_safe_validate | provider_error", extra={"tag": label, "error": str(e)})
        return _ValidateOutcome(tag=label, result=None, error=str(e))
