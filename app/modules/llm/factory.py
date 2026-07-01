from __future__ import annotations

from app.config import settings
from app.core.exceptions import LLMError
from app.core.logging import get_logger
from app.modules.llm.base import LLMProvider
from app.modules.llm.aria import AriaProvider
from app.modules.llm.bedrock import BedrockProvider
from app.modules.llm.gemini import GeminiProvider
from app.modules.llm.ollama import OllamaProvider

logger = get_logger(__name__)

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "gemini": GeminiProvider,
    "bedrock": BedrockProvider,
    "ollama": OllamaProvider,
    "aria": AriaProvider,
}

_CACHE: dict[str, LLMProvider] = {}

DEFAULT_PROVIDER: str = settings.LLM_PROVIDER.lower().strip() or "gemini"


def get_llm_provider(name: str | None = None) -> LLMProvider:
    tag = (name or DEFAULT_PROVIDER).lower().strip()
    if tag in _CACHE:
        return _CACHE[tag]

    cls = _PROVIDERS.get(tag)
    if cls is None:
        raise LLMError(f"Unknown LLM provider tag: '{tag}'. Available: {list(_PROVIDERS.keys())}")

    logger.info("get_llm_provider | criando", extra={"provider": tag})
    instance = cls()
    _CACHE[tag] = instance
    return instance


def available_providers() -> list[str]:
    return list(_PROVIDERS.keys())
