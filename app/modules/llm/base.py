from __future__ import annotations

from PIL import Image
from pydantic import BaseModel


class LLMResponse(BaseModel):
    ok: bool
    reason: str
    confidence: float
    tokens_input: int
    tokens_output: int
    model_used: str


class LLMProvider:
    async def validate(
        self,
        pages: list[Image.Image],
        regra: str | None,
        ocr_text: str,
    ) -> LLMResponse:
        raise NotImplementedError
