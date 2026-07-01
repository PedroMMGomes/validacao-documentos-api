import base64
import io
import json

import httpx
from PIL import Image

from app.config import settings
from app.core.exceptions import LLMError
from app.core.logging import get_logger
from app.modules.llm.base import LLMProvider, LLMResponse

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "Voce e um validador Senior de documentos medicos para plano de saude. Reprove todos documentos invalidos ou se nao atender a todos requisitos atendidos. Seja criterioso. "
    "Responda APENAS com JSON valido: "
    '{"ok": true|false, "reason": "<motivo em pt-BR, 1 frase>", "confidence": <0.0-1.0>}'
)


class OllamaProvider(LLMProvider):
    def __init__(self):
        self._base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self._model = settings.OLLAMA_MODEL
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=settings.LLM_TIMEOUT_SECONDS,
                limits=httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=10,
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
        logger.info("ollama_validate | inicio", extra={"pages": len(pages), "model": self._model})

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        regra_text = f"Regra de avaliacao: {regra}\n\n" if regra else ""
        if ocr_text:
            regra_text += f"Texto extraido por OCR (referencia):\n{ocr_text}\n\n"

        user_content = regra_text if regra_text else "Analise este documento medico."

        msg = {"role": "user", "content": user_content}

        if pages:
            buf = io.BytesIO()
            pages[0].save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            msg["images"] = [b64]

        messages.append(msg)

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1},
        }

        try:
            client = self._get_client()
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()

            data = resp.json()
            output_text = data.get("message", {}).get("content", "")
            if not output_text:
                raise LLMError("Ollama returned empty response")

            parsed = _parse_ollama_json(output_text)

            result = LLMResponse(
                ok=parsed["ok"],
                reason=parsed["reason"],
                confidence=parsed["confidence"],
                tokens_input=data.get("prompt_eval_count", 0) or 0,
                tokens_output=data.get("eval_count", 0) or 0,
                model_used=self._model,
            )

            logger.info("ollama_validate | ok", extra={"ok": result.ok, "confidence": result.confidence})
            return result

        except LLMError:
            raise
        except httpx.TimeoutException as e:
            raise LLMError(f"Ollama timeout: {str(e)}") from e
        except Exception as e:
            logger.error("ollama_validate | erro", extra={"error": str(e)})
            raise LLMError(f"Ollama error: {str(e)}") from e


def _parse_ollama_json(text: str) -> dict:
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
        raise LLMError(f"Invalid JSON from Ollama: {text[:200]}") from e

    if "ok" not in data or "reason" not in data or "confidence" not in data:
        raise LLMError(f"Missing fields in Ollama response: {data}")

    return {"ok": bool(data["ok"]), "reason": str(data["reason"]), "confidence": float(data["confidence"])}
