import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from app.config import settings
from app.core.logging import get_logger
from app.modules.vision_jpeg import page_to_jpeg_bytes

logger = get_logger(__name__)

MANIFEST_VERSION = 1


def _is_enabled() -> bool:
    return bool(settings.REQUEST_ARTIFACTS_PATH)


def _base_path() -> Path:
    return Path(settings.REQUEST_ARTIFACTS_PATH)


def _artifact_dir(api_key_id: uuid.UUID, request_id: uuid.UUID) -> Path:
    return _base_path() / str(api_key_id) / str(request_id)


def _sync_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _sync_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


def _sync_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sanitize_ext(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    allowed = {"pdf", "jpg", "jpeg", "png", "tiff", "tif", "bin"}
    return ext if ext in allowed else "bin"


async def init_artifact_dir(
    api_key_id: uuid.UUID,
    request_id: uuid.UUID,
) -> Path | None:
    if not _is_enabled():
        return None
    d = _artifact_dir(api_key_id, request_id)
    await asyncio.to_thread(d.mkdir, parents=True, exist_ok=True)

    for sub in ("normalized", "providers", "errors"):
        (d / sub).mkdir(parents=True, exist_ok=True)

    manifest_path = d / "manifest.json"
    manifest = _build_manifest_skeleton(request_id, api_key_id, complete=False)
    await asyncio.to_thread(_sync_write_json, manifest_path, manifest)

    logger.info(
        "artifacts | init_dir",
        extra={"api_key_id": str(api_key_id), "request_id": str(request_id), "path": str(d)},
    )
    return d


async def write_meta(
    artifact_dir: Path | None,
    *,
    request_id: uuid.UUID,
    api_key_id: uuid.UUID,
    tenant_id: uuid.UUID,
    filename_original: str,
    document_type: str | None,
    regra_len: int,
    llm_providers: list[str],
    file_content: bytes,
    storage_path_uuid: uuid.UUID | None = None,
) -> None:
    if artifact_dir is None:
        return
    meta = {
        "request_id": str(request_id),
        "api_key_id": str(api_key_id),
        "tenant_id": str(tenant_id),
        "filename_original": filename_original,
        "document_type": document_type,
        "regra_len": regra_len,
        "llm_providers": llm_providers,
        "file_sha256": _file_sha256(file_content),
        "file_size_bytes": len(file_content),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if storage_path_uuid is not None:
        meta["storage_path_uuid"] = str(storage_path_uuid)
    await asyncio.to_thread(_sync_write_json, artifact_dir / "meta.json", meta)
    logger.info(
        "artifacts | write_meta",
        extra={"request_id": str(request_id), "path": str(artifact_dir / "meta.json")},
    )


async def write_original(
    artifact_dir: Path | None,
    content: bytes,
    filename: str,
) -> None:
    if artifact_dir is None:
        return
    ext = _sanitize_ext(filename)
    dest = artifact_dir / f"original.{ext}"
    await asyncio.to_thread(_sync_write_bytes, dest, content)
    logger.info(
        "artifacts | write_original",
        extra={"path": str(dest), "size": len(content)},
    )


async def write_normalized(
    artifact_dir: Path | None,
    pages: list[Image.Image],
    ocr_text: str,
) -> None:
    if artifact_dir is None:
        return
    norm_dir = artifact_dir / "normalized"
    norm_dir.mkdir(parents=True, exist_ok=True)

    def _sync_write_normalized() -> list[str]:
        written: list[str] = []
        for i, page in enumerate(pages):
            jpeg_bytes = page_to_jpeg_bytes(page, settings.LLM_JPEG_QUALITY)
            fname = f"page_{i + 1:03d}.jpg"
            (norm_dir / fname).write_bytes(jpeg_bytes)
            written.append(f"normalized/{fname}")
        if ocr_text:
            (norm_dir / "ocr.txt").write_text(ocr_text, encoding="utf-8")
            written.append("normalized/ocr.txt")
        return written

    written = await asyncio.to_thread(_sync_write_normalized)
    logger.info(
        "artifacts | write_normalized",
        extra={"pages": len(pages), "files_written": len(written)},
    )


async def write_provider(
    artifact_dir: Path | None,
    tag: str,
    payload: dict[str, Any],
) -> None:
    if artifact_dir is None:
        return
    dest = artifact_dir / "providers" / f"{tag}.json"
    await asyncio.to_thread(_sync_write_json, dest, payload)
    logger.info("artifacts | write_provider", extra={"tag": tag, "path": str(dest)})


async def write_response(
    artifact_dir: Path | None,
    response_dict: dict[str, Any],
) -> None:
    if artifact_dir is None:
        return
    dest = artifact_dir / "response.json"
    await asyncio.to_thread(_sync_write_json, dest, response_dict)
    logger.info("artifacts | write_response", extra={"path": str(dest)})


async def write_error(
    artifact_dir: Path | None,
    error_dict: dict[str, Any],
) -> None:
    if artifact_dir is None:
        return
    dest = artifact_dir / "errors" / "pipeline.json"
    await asyncio.to_thread(_sync_write_json, dest, error_dict)
    logger.info("artifacts | write_error", extra={"path": str(dest)})


async def finalize_manifest(
    artifact_dir: Path | None,
    *,
    api_key_id: uuid.UUID,
    request_id: uuid.UUID,
    complete: bool,
) -> None:
    if artifact_dir is None:
        return

    def _sync_finalize() -> None:
        files: list[dict[str, str]] = []
        for p in sorted(artifact_dir.rglob("*")):
            if p.is_file() and p.name != "manifest.json":
                rel = p.relative_to(artifact_dir).as_posix()
                role = _classify_role(rel)
                entry: dict[str, str] = {"relative_path": rel, "role": role}
                try:
                    sha = hashlib.sha256(p.read_bytes()).hexdigest()
                    entry["sha256"] = sha
                except Exception:
                    pass
                files.append(entry)

        manifest = _build_manifest_skeleton(request_id, api_key_id, complete)
        manifest["files"] = files
        _sync_write_json(artifact_dir / "manifest.json", manifest)

    await asyncio.to_thread(_sync_finalize)
    logger.info(
        "artifacts | finalize_manifest",
        extra={"request_id": str(request_id), "complete": complete},
    )


def _build_manifest_skeleton(
    request_id: uuid.UUID,
    api_key_id: uuid.UUID,
    complete: bool,
) -> dict[str, Any]:
    return {
        "request_id": str(request_id),
        "api_key_id": str(api_key_id),
        "version": MANIFEST_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": complete,
        "files": [],
    }


def _classify_role(rel_path: str) -> str:
    if rel_path == "meta.json":
        return "meta"
    if rel_path.startswith("normalized/"):
        return "normalized"
    if rel_path.startswith("providers/"):
        return "provider"
    if rel_path.startswith("errors/"):
        return "error"
    if rel_path == "response.json":
        return "response"
    if rel_path.startswith("original."):
        return "original"
    return "other"
