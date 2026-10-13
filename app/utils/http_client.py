import httpx

from app.config import settings
from app.utils.ssrf import validate_safe_url


async def check_redirect_ssrf(response: httpx.Response) -> None:
    """Validate that redirect target URLs do not point to restricted IP addresses."""
    if response.is_redirect:
        location = response.headers.get("location")
        if location:
            target_url = str(response.url.join(location))
            validate_safe_url(target_url)


async def create_client() -> httpx.AsyncClient:
    """Create and return a configured httpx AsyncClient."""
    return httpx.AsyncClient(
        http2=True,
        timeout=httpx.Timeout(
            connect=10.0,
            read=float(settings.DOWNLOAD_TIMEOUT_SECONDS),
            write=10.0,
            pool=5.0,
        ),
        limits=httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
        ),
        follow_redirects=True,
        headers={"User-Agent": "DocumentExtractor/1.0"},
        event_hooks={"response": [check_redirect_ssrf]},
    )


async def close_client(client: httpx.AsyncClient) -> None:
    """Close the httpx AsyncClient."""
    await client.aclose()
