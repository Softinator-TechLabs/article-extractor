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
    model_config = {
        "env_prefix": "",
        "env_file": ".env",
        "env_file_encoding": "utf-8"
    }


settings = Settings()
