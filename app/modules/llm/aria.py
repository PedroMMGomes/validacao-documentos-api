from app.core.exceptions import LLMError
from app.core.logging import get_logger
from app.modules.llm.base import LLMProvider, LLMResponse

logger = get_logger(__name__)

# TODO(Pedro): definir endpoint, autenticacao e payload do Aria LLM.
# Substituir este stub pela integracao real quando as credenciais e SDK forem definidos.


class AriaProvider(LLMProvider):
    async def validate(self, pages, regra, ocr_text) -> LLMResponse:
        raise LLMError("AriaProvider nao implementado — configure credenciais e endpoint")
