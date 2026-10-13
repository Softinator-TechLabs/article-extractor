import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    MAX_WORKERS: int = (os.cpu_count() or 2) * 2
    MAX_CONCURRENT_DOWNLOADS: int = 10
    DOWNLOAD_TIMEOUT_SECONDS: int = 30
    MAX_FILE_SIZE_MB: int = 50
    REQUEST_TIMEOUT_SECONDS: int = 120
    LOG_LEVEL: str = "INFO"

    API_KEY: str | None = None
    REQUIRE_API_KEY: bool = True
    ENVIRONMENT: str = "development"
    ENABLE_DOCS: bool | None = None
    ENABLE_SSRF_PROTECTION: bool = True
    ALLOWED_HOSTS: list[str] = ["*"]
    WEB_CONCURRENCY: int = 2
    CACHE_TTL_SECONDS: int = 3600

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def docs_enabled(self) -> bool:
        if self.ENABLE_DOCS is not None:
            return self.ENABLE_DOCS
        return not self.is_production

    # OCR Fallback Configuration
    ENABLE_OCR_FALLBACK: bool = True
    OCR_LANGUAGE: str = "eng"
    OCR_CHARS_PER_PAGE_THRESHOLD: int = 50

    model_config = {
        "env_prefix": "",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
