import base64
import io
import json

import httpx
from PIL import Image

from app.config import settings
from app.core.exceptions import LLMError
from app.core.logging import get_logger
from app.modules.llm.base import LLMProvider, LLMResponse
from app.modules.vision_jpeg import page_to_jpeg_bytes

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "Voce e um validador Senior de documentos medicos para plano de saude. Reprove todos documentos invalidos ou se nao atender a todos requisitos atendidos. Seja criterioso. "
    "Responda APENAS com JSON valido: "
    '{"ok": true|false, "reason": "<motivo em pt-BR, 1 frase>", "confidence": <0.0-1.0>}'
)


class BedrockProvider(LLMProvider):
    def __init__(self):
        api_key = settings.BEDROCK_API_KEY
        if not api_key:
            raise LLMError(
                "BEDROCK_API_KEY nao configurado. "
                "Defina no .env a Bedrock API Key gerada no console AWS (Bedrock > API Keys)."
            )
        self._api_key = api_key
        self._model_id = settings.BEDROCK_MODEL_ID
        self._url = (
            f"https://bedrock-runtime.{settings.AWS_REGION}.amazonaws.com"
            f"/model/{self._model_id}/converse"
        )
        self._client: httpx.AsyncClient | None = None
        logger.info(
            "BedrockProvider | inicializado",
            extra={"region": settings.AWS_REGION, "model": self._model_id},
        )

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=settings.LLM_TIMEOUT_SECONDS,
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                    keepalive_expiry=60,
                ),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def validate(
        self,
        pages: list[Image.Image],
        regra: str | None,
        ocr_text: str,
    ) -> LLMResponse:
        logger.info("bedrock_validate | inicio", extra={"pages": len(pages), "model": self._model_id})

        content_blocks = []
        raw_image_bytes_total = 0

        for page in pages:
            if settings.BEDROCK_IMAGE_USE_JPEG:
                raw = page_to_jpeg_bytes(page, settings.LLM_JPEG_QUALITY)
                fmt = "jpeg"
            else:
                buf = io.BytesIO()
                page.save(buf, format="PNG")
                raw = buf.getvalue()
                fmt = "png"
            raw_image_bytes_total += len(raw)
            b64 = base64.b64encode(raw).decode("utf-8")
            content_blocks.append({"image": {"format": fmt, "source": {"bytes": b64}}})

        logger.info(
            "bedrock_validate | payload_imagens",
            extra={
                "pages": len(pages),
                "image_raw_bytes_total": raw_image_bytes_total,
                "format": "jpeg" if settings.BEDROCK_IMAGE_USE_JPEG else "png",
            },
        )

        regra_text = f"Regra de avaliacao: {regra}\n\n" if regra else ""
        if ocr_text:
            regra_text += f"Texto extraido por OCR (referencia):\n{ocr_text}\n\n"

        content_blocks.append({"text": regra_text if regra_text else "Analise este documento medico."})

        payload = {
            "system": [{"text": SYSTEM_PROMPT}],
            "messages": [{"role": "user", "content": content_blocks}],
            "inferenceConfig": {"maxTokens": 1024},
        }

        try:
            client = self._get_client()
            resp = await client.post(
                self._url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )

            if resp.status_code != 200:
                body = resp.text[:500]
                logger.error("bedrock_validate | http_error", extra={"status": resp.status_code, "body": body})
                raise LLMError(f"Bedrock HTTP {resp.status_code}: {body}")

            data = resp.json()
            output_text = data["output"]["message"]["content"][0]["text"]
            parsed = _parse_llm_json(output_text)

            usage = data.get("usage", {})
            result = LLMResponse(
                ok=parsed["ok"],
                reason=parsed["reason"],
                confidence=parsed["confidence"],
                tokens_input=usage.get("inputTokens", 0),
                tokens_output=usage.get("outputTokens", 0),
                model_used=self._model_id,
            )

            logger.info("bedrock_validate | ok", extra={"ok": result.ok, "confidence": result.confidence})
            return result

        except LLMError:
            raise
        except httpx.TimeoutException as e:
            logger.error("bedrock_validate | timeout", extra={"error": str(e)})
            raise LLMError(f"Bedrock timeout: {str(e)}") from e
        except Exception as e:
            logger.error("bedrock_validate | erro", extra={"error": str(e)})
            raise LLMError(f"Bedrock error: {str(e)}") from e


def _parse_llm_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"Invalid JSON from Bedrock: {text[:200]}") from e

    if "ok" not in data or "reason" not in data or "confidence" not in data:
        raise LLMError(f"Missing fields in Bedrock response: {data}")

    return {"ok": bool(data["ok"]), "reason": str(data["reason"]), "confidence": float(data["confidence"])}
