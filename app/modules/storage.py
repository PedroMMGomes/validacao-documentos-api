import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.core.exceptions import UnsupportedFormatError
from app.core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "tiff", "tif"}


def _get_extension(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext


def validate_extension(filename: str) -> str:
    ext = _get_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        logger.warning("validate_extension | formato_nao_suportado", extra={"filename": filename, "ext": ext})
        raise UnsupportedFormatError(f"Formato '{ext}' nao suportado. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    return ext


async def save_file(tenant_id: uuid.UUID, request_id: uuid.UUID, filename: str, content: bytes) -> str:
    ext = validate_extension(filename)
    now = datetime.utcnow()
    relative_path = f"{tenant_id}/{now.year}/{now.month:02d}/{request_id}.{ext}"
    full_path = Path(settings.STORAGE_PATH) / relative_path

    full_path.parent.mkdir(parents=True, exist_ok=True)

    await asyncio.to_thread(_write_file, full_path, content)

    logger.info(
        "save_file | ok",
        extra={"tenant_id": str(tenant_id), "request_id": str(request_id), "path": str(full_path), "size": len(content)},
    )
    return relative_path


async def read_file(relative_path: str) -> bytes:
    full_path = Path(settings.STORAGE_PATH) / relative_path
    return await asyncio.to_thread(_read_file, full_path)


def _write_file(path: Path, content: bytes) -> None:
    with open(path, "wb") as f:
        f.write(content)


def _read_file(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()
