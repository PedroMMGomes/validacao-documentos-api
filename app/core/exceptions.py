from fastapi import HTTPException


class InvalidAPIKeyError(HTTPException):
    def __init__(self, detail: str = "Invalid API Key"):
        super().__init__(status_code=401, detail={"error_code": "INVALID_API_KEY", "message": detail})


class QuotaExceededError(HTTPException):
    def __init__(self, detail: str = "Daily quota exceeded"):
        super().__init__(status_code=429, detail={"error_code": "QUOTA_EXCEEDED", "message": detail})


class UnsupportedFormatError(HTTPException):
    def __init__(self, detail: str = "Unsupported file format"):
        super().__init__(status_code=422, detail={"error_code": "UNSUPPORTED_FORMAT", "message": detail})


class LLMTimeoutError(HTTPException):
    def __init__(self, detail: str = "LLM provider timeout"):
        super().__init__(status_code=504, detail={"error_code": "LLM_TIMEOUT", "message": detail})


class LLMError(HTTPException):
    def __init__(self, detail: str = "LLM provider error"):
        super().__init__(status_code=502, detail={"error_code": "LLM_ERROR", "message": detail})
