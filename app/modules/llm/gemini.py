import json

import google.generativeai as genai
from PIL import Image

from app.config import settings
from app.core.exceptions import LLMError, LLMTimeoutError
from app.core.logging import get_logger
from app.modules.llm.base import LLMProvider, LLMResponse
from app.modules.vision_jpeg import page_to_jpeg_bytes

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "Voce e um validador Senior de documentos medicos para plano de saude. Reprove todos documentos invalidos ou se nao atender a todos requisitos atendidos. Seja criterioso. "
    "Responda APENAS com JSON valido: "
    '{"ok": true|false, "reason": "<motivo em pt-BR, 1 frase>", "confidence": <0.0-1.0>}'
)


class GeminiProvider(LLMProvider):
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._model_name = settings.GEMINI_MODEL
        self._model = genai.GenerativeModel(
            self._model_name,
            system_instruction=SYSTEM_PROMPT,
            generation_config=genai.types.GenerationConfig(temperature=0.1),
        )

    async def validate(
        self,
        pages: list[Image.Image],
        regra: str | None,
        ocr_text: str,
    ) -> LLMResponse:
        jpeg_bytes_total = sum(len(page_to_jpeg_bytes(p, settings.LLM_JPEG_QUALITY)) for p in pages)
        logger.info(
            "gemini_validate | inicio",
            extra={
                "pages": len(pages),
                "ocr_len": len(ocr_text),
                "image_jpeg_bytes_total": jpeg_bytes_total,
                "jpeg_quality": settings.LLM_JPEG_QUALITY,
            },
        )

        try:
            regra_text = f"Regra de avaliacao: {regra}\n\n" if regra else ""
            if ocr_text:
                regra_text += f"Texto extraido por OCR (referencia):\n{ocr_text}\n\n"

            prompt_parts = [regra_text if regra_text else "Analise este documento medico."]
            for page in pages:
                prompt_parts.append(page)

            response = await self._model.generate_content_async(prompt_parts)

            if not response.text:
                raise LLMError("Gemini returned empty response")

            parsed = _parse_response(response.text)
            usage = response.usage_metadata

            result = LLMResponse(
                ok=parsed["ok"],
                reason=parsed["reason"],
                confidence=parsed["confidence"],
                tokens_input=getattr(usage, "prompt_token_count", 0) or 0,
                tokens_output=getattr(usage, "candidates_token_count", 0) or 0,
                model_used=self._model_name,
            )

            logger.info(
                "gemini_validate | ok",
                extra={"ok": result.ok, "confidence": result.confidence, "tokens_input": result.tokens_input},
            )
            return result

        except (LLMError, LLMTimeoutError):
            raise
        except Exception as e:
            logger.error("gemini_validate | erro", extra={"error": str(e)})
            raise LLMError(f"Gemini error: {str(e)}") from e


def _parse_response(text: str) -> dict:
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
        logger.error("_parse_response | json_invalido", extra={"raw": text[:200], "error": str(e)})
        raise LLMError(f"Invalid JSON from LLM: {text[:200]}") from e

    if "ok" not in data or "reason" not in data or "confidence" not in data:
        raise LLMError(f"Missing fields in LLM response: {data}")

    return {
        "ok": bool(data["ok"]),
        "reason": str(data["reason"]),
        "confidence": float(data["confidence"]),
    }
