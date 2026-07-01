import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import get_logger, setup_logging
from app.modules.llm.factory import get_llm_provider
from app.routers import admin_keys, billing, dashboard, health, requests, validate


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        log = get_logger("http")
        correlation_id = str(uuid.uuid4())
        t0 = time.perf_counter()
        log.info(
            "http_request | inicio",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "query": str(request.query_params) if request.query_params else "",
                "client_host": request.client.host if request.client else "",
            },
        )
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            log.error(
                "http_request | excecao",
                extra={"correlation_id": correlation_id, "path": request.url.path, "elapsed_ms": elapsed_ms},
            )
            raise
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        log.info(
            "http_request | fim",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
            },
        )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    log = get_logger("lifespan")
    log.info("lifespan | startup_inicio")

    from app.modules.llm.factory import _CACHE, available_providers

    for tag in available_providers():
        try:
            get_llm_provider(tag)
            log.info("lifespan | provider_preinicializado", extra={"provider": tag})
        except Exception as e:
            log.warning("lifespan | provider_skip", extra={"provider": tag, "error": str(e)})

    yield

    log.info("lifespan | shutdown_inicio")
    for tag, provider in _CACHE.items():
        close_fn = getattr(provider, "close", None)
        if close_fn:
            try:
                await close_fn()
                log.info("lifespan | provider_fechado", extra={"provider": tag})
            except Exception as e:
                log.warning("lifespan | provider_close_erro", extra={"provider": tag, "error": str(e)})
    log.info("lifespan | shutdown_fim")


app = FastAPI(
    title="API de Validacao de Documentos Medicos",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)

app.include_router(validate.router)
app.include_router(requests.router)
app.include_router(billing.router)
app.include_router(health.router)
app.include_router(admin_keys.router)
app.include_router(dashboard.router)
