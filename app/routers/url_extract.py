import asyncio
import logging
from typing import Optional, Union

from fastapi import APIRouter, Request
from pydantic import BaseModel, HttpUrl, field_validator

from app.config import settings
from app.utils.format_router import detect_format, get_extractor, UnsupportedFormatError

logger = logging.getLogger(__name__)

router = APIRouter()


class URLExtractRequest(BaseModel):
    urls: list[HttpUrl]

    @field_validator("urls")
    @classmethod
    def urls_not_empty(cls, v):
        if not v:
            raise ValueError("urls list cannot be empty")
        if len(v) > 50:
            raise ValueError("max 50 URLs per request")
        return v


class URLExtractResult(BaseModel):
    url: str
    content: Optional[str] = None
    error: Optional[str] = None


class SingleURLExtractRequest(BaseModel):
    article_pdf_link: HttpUrl


class SingleURLExtractResult(BaseModel):
    content: Optional[str] = None
    error: Optional[str] = None


class FileTooLargeError(Exception):
    """Raised when a downloaded file exceeds the size limit."""
    pass


async def _process_url(
    url: str,
    client,
    executor,
    download_semaphore: asyncio.Semaphore,
    extraction_semaphore: asyncio.Semaphore,
) -> URLExtractResult:
    """Download and extract text from a single URL."""
    try:
        async with download_semaphore:
            async with client.stream("GET", url) as response:
                response.raise_for_status()

                # Check Content-Length before reading
                content_length = int(response.headers.get("content-length", 0))
                max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
                if content_length > max_bytes:
                    raise FileTooLargeError(
                        f"File too large: {content_length} bytes "
                        f"(limit: {settings.MAX_FILE_SIZE_MB} MB)"
                    )

                # Stream and accumulate bytes
                chunks: list[bytes] = []
                total_size = 0
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    total_size += len(chunk)
                    if total_size > max_bytes:
                        raise FileTooLargeError(
                            f"File too large: exceeded {settings.MAX_FILE_SIZE_MB} MB during download"
                        )
                    chunks.append(chunk)

                content = b"".join(chunks)
                content_type = response.headers.get("content-type")

        # Detect format
        fmt = detect_format(content, filename=url, content_type=content_type)

        # Extract text
        extractor = get_extractor(fmt, executor)
        async with extraction_semaphore:
            text = await extractor.extract(content, filename=url)

        return URLExtractResult(url=url, content=text, error=None)

    except UnsupportedFormatError as exc:
        logger.warning("Unsupported format for URL %s: %s", url, exc)
        return URLExtractResult(url=url, content=None, error=str(exc))
    except FileTooLargeError as exc:
        logger.warning("File too large for URL %s: %s", url, exc)
        return URLExtractResult(url=url, content=None, error=str(exc))
    except Exception as exc:
        logger.warning("Failed to process URL %s: %s (%s)", url, exc, type(exc).__name__)
        return URLExtractResult(url=url, content=None, error=f"{type(exc).__name__}: {exc}")


@router.post("/urls", response_model=list[URLExtractResult])
async def extract_urls(body: URLExtractRequest, request: Request):
    """Extract text from documents at the given URLs.

    Always returns HTTP 200. Per-item errors are in the `error` field.
    """
    client = request.app.state.http_client
    executor = request.app.state.executor
    download_semaphore = request.app.state.download_semaphore
    extraction_semaphore = request.app.state.extraction_semaphore

    tasks = [
        _process_url(str(url), client, executor, download_semaphore, extraction_semaphore)
        for url in body.urls
    ]

    results = await asyncio.gather(*tasks)
    return list(results)


@router.post("/article-url", response_model=Union[SingleURLExtractResult, list[SingleURLExtractResult]])
async def extract_article_url(
    body: Union[SingleURLExtractRequest, list[SingleURLExtractRequest]], 
    request: Request
):
    """Extract text from one or multiple article PDF links.
    
    Accepts either a single JSON object or an array of JSON objects.
    Returns a single result object or an array of result objects respectively.
    """
    client = request.app.state.http_client
    executor = request.app.state.executor
    download_semaphore = request.app.state.download_semaphore
    extraction_semaphore = request.app.state.extraction_semaphore

    is_list = isinstance(body, list)
    items = body if is_list else [body]

    tasks = [
        _process_url(
            str(item.article_pdf_link), 
            client, 
            executor, 
            download_semaphore, 
            extraction_semaphore
        )
        for item in items
    ]

    results = await asyncio.gather(*tasks)
    
    formatted_results = [
        SingleURLExtractResult(content=r.content, error=r.error)
        for r in results
    ]

    return formatted_results if is_list else formatted_results[0]
