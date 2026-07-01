import json
import shutil
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.modules import artifacts


@pytest.fixture
def tmp_artifacts_path(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    with patch.object(artifacts.settings, "REQUEST_ARTIFACTS_PATH", str(artifacts_dir)):
        yield artifacts_dir


@pytest.fixture
def sample_api_key_id():
    return uuid.uuid4()


@pytest.fixture
def sample_request_id():
    return uuid.uuid4()


@pytest.fixture
def sample_tenant_id():
    return uuid.uuid4()


@pytest.fixture
def sample_jpeg_content():
    img = Image.new("RGB", (100, 100), color="red")
    import io

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def sample_pages():
    return [
        Image.new("RGB", (200, 300), color="blue"),
        Image.new("RGB", (150, 150), color="green"),
    ]


def _artifact_dir(base: Path, api_key_id: uuid.UUID, request_id: uuid.UUID) -> Path:
    return base / str(api_key_id) / str(request_id)


async def test_full_pipeline_artifacts(
    tmp_artifacts_path,
    sample_api_key_id,
    sample_request_id,
    sample_tenant_id,
    sample_jpeg_content,
    sample_pages,
):
    ad = await artifacts.init_artifact_dir(sample_api_key_id, sample_request_id)
    assert ad is not None
    assert ad.exists()
    assert (ad / "normalized").exists()
    assert (ad / "providers").exists()
    assert (ad / "errors").exists()

    manifest_path = ad / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["complete"] is False
    assert manifest["request_id"] == str(sample_request_id)
    assert manifest["version"] == 1

    await artifacts.write_meta(
        ad,
        request_id=sample_request_id,
        api_key_id=sample_api_key_id,
        tenant_id=sample_tenant_id,
        filename_original="relatorio.pdf",
        document_type="laudo_medico",
        regra_len=42,
        llm_providers=["gemini", "bedrock"],
        file_content=sample_jpeg_content,
    )
    meta = json.loads((ad / "meta.json").read_bytes())
    assert meta["filename_original"] == "relatorio.pdf"
    assert meta["document_type"] == "laudo_medico"
    assert meta["regra_len"] == 42
    assert meta["llm_providers"] == ["gemini", "bedrock"]
    assert len(meta["file_sha256"]) == 64
    assert meta["file_size_bytes"] == len(sample_jpeg_content)

    await artifacts.write_original(ad, sample_jpeg_content, "relatorio.pdf")
    assert (ad / "original.pdf").exists()
    assert (ad / "original.pdf").read_bytes() == sample_jpeg_content

    await artifacts.write_normalized(ad, sample_pages, "texto OCR aqui")
    norm_dir = ad / "normalized"
    assert (norm_dir / "page_001.jpg").exists()
    assert (norm_dir / "page_002.jpg").exists()
    assert (norm_dir / "ocr.txt").exists()
    assert (norm_dir / "ocr.txt").read_text(encoding="utf-8") == "texto OCR aqui"

    await artifacts.write_provider(ad, "gemini", {"tag": "gemini", "ok": True, "reason": "valido"})
    await artifacts.write_provider(ad, "bedrock", {"tag": "bedrock", "ok": False, "reason": "invalido"})
    assert (ad / "providers" / "gemini.json").exists()
    assert (ad / "providers" / "bedrock.json").exists()
    gemini_data = json.loads((ad / "providers" / "gemini.json").read_bytes())
    assert gemini_data["ok"] is True

    response_dict = {
        "request_id": str(sample_request_id),
        "status": "rejected",
        "ok": False,
        "reason": "bedrock rejected",
        "artifacts_manifest_url": f"http://localhost:8000/v1/requests/{sample_request_id}/artifacts/manifest",
    }
    await artifacts.write_response(ad, response_dict)
    resp = json.loads((ad / "response.json").read_bytes())
    assert resp["status"] == "rejected"

    await artifacts.finalize_manifest(ad, api_key_id=sample_api_key_id, request_id=sample_request_id, complete=True)
    manifest = json.loads((ad / "manifest.json").read_bytes())
    assert manifest["complete"] is True
    assert len(manifest["files"]) >= 7  # meta, original, 2 pages, ocr, 2 providers, response

    roles = {f["role"] for f in manifest["files"]}
    assert "original" in roles
    assert "normalized" in roles
    assert "provider" in roles
    assert "response" in roles
    assert "meta" in roles


async def test_error_pipeline_artifacts(
    tmp_artifacts_path,
    sample_api_key_id,
    sample_request_id,
):
    ad = await artifacts.init_artifact_dir(sample_api_key_id, sample_request_id)

    await artifacts.write_error(ad, {"error_code": "INTERNAL_ERROR", "message": "something broke"})
    assert (ad / "errors" / "pipeline.json").exists()

    error_data = json.loads((ad / "errors" / "pipeline.json").read_bytes())
    assert error_data["error_code"] == "INTERNAL_ERROR"

    await artifacts.finalize_manifest(ad, api_key_id=sample_api_key_id, request_id=sample_request_id, complete=False)
    manifest = json.loads((ad / "manifest.json").read_bytes())
    assert manifest["complete"] is False


async def test_noop_when_disabled(
    tmp_path,
    sample_api_key_id,
    sample_request_id,
    sample_jpeg_content,
):
    with patch.object(artifacts.settings, "REQUEST_ARTIFACTS_PATH", ""):
        result = await artifacts.init_artifact_dir(sample_api_key_id, sample_request_id)
        assert result is None

        await artifacts.write_original(None, sample_jpeg_content, "test.jpg")
        await artifacts.write_meta(
            None,
            request_id=sample_request_id,
            api_key_id=sample_api_key_id,
            tenant_id=uuid.uuid4(),
            filename_original="test.jpg",
            document_type=None,
            regra_len=0,
            llm_providers=[],
            file_content=sample_jpeg_content,
        )
        await artifacts.write_normalized(None, [], "")
        await artifacts.write_provider(None, "test", {})
        await artifacts.write_response(None, {})
        await artifacts.write_error(None, {})
        await artifacts.finalize_manifest(None, api_key_id=sample_api_key_id, request_id=sample_request_id, complete=True)


async def test_normalized_without_ocr(
    tmp_artifacts_path,
    sample_api_key_id,
    sample_request_id,
    sample_pages,
):
    ad = await artifacts.init_artifact_dir(sample_api_key_id, sample_request_id)
    await artifacts.write_normalized(ad, sample_pages, "")
    norm_dir = ad / "normalized"
    assert (norm_dir / "page_001.jpg").exists()
    assert (norm_dir / "page_002.jpg").exists()
    assert not (norm_dir / "ocr.txt").exists()
