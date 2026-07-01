from pathlib import Path
from urllib.parse import urlparse, parse_qs

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/validacao"
    STORAGE_PATH: str = "./storage"

    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = ""
    AWS_REGION: str = "us-east-1"
    BEDROCK_MODEL_ID: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    BEDROCK_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma3:4b"

    MAX_TOKENS_INPUT: int = 100_000
    LLM_TIMEOUT_SECONDS: int = 60
    MAX_CONCURRENT_REQUESTS: int = 200

    PDF_RENDER_DPI: int = Field(default=120, ge=72, le=400)
    NORMALIZE_MAX_LONG_EDGE: int = Field(default=2048, ge=256, le=8192)
    LLM_JPEG_QUALITY: int = Field(default=85, ge=40, le=100)
    BEDROCK_IMAGE_USE_JPEG: bool = True

    ADMIN_API_KEY: str = ""

    REQUEST_ARTIFACTS_PATH: str = ""
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    model_config = {
        "env_file": str(Path(__file__).resolve().parent.parent / ".env"),
        "env_file_encoding": "utf-8",
    }

    @model_validator(mode="after")
    def _parse_gemini_url(self) -> "Settings":
        if self.GEMINI_API_KEY.startswith("http"):
            parsed = urlparse(self.GEMINI_API_KEY)
            qs = parse_qs(parsed.query)
            self.GEMINI_API_KEY = qs.get("key", [""])[0]
            path_parts = parsed.path.split("/")
            for i, part in enumerate(path_parts):
                if part == "models" and i + 1 < len(path_parts):
                    model_segment = path_parts[i + 1]
                    if ":" in model_segment:
                        model_segment = model_segment.split(":")[0]
                    if not self.GEMINI_MODEL:
                        self.GEMINI_MODEL = model_segment
                    break
        if not self.GEMINI_MODEL:
            self.GEMINI_MODEL = "gemini-2.0-flash"

        self.BEDROCK_API_KEY = (self.BEDROCK_API_KEY or "").strip()
        return self


settings = Settings()
