import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key(api_key_header: str | None = Security(api_key_header)) -> str:
    """Verify the X-API-Key header matches the configured API_KEY in constant time."""
    if not settings.API_KEY:
        if settings.is_production and settings.REQUIRE_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API_KEY is not configured on the server",
            )
        return ""

    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header missing",
        )

    if not secrets.compare_digest(api_key_header, settings.API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

    return api_key_header
