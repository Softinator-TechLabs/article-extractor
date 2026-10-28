import asyncio
import logging

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, HttpUrl, field_validator

from app.config import settings
from app.utils.cache import url_cache
from app.utils.format_router import UnsupportedFormatError, detect_format, get_extractor
from app.utils.sanitizer import sanitize_surrogates
from app.utils.ssrf import SSRFBlockedError, validate_safe_url

logger = logging.getLogger(__name__)

router = APIRouter()


class URLExtractRequest(BaseModel):
    urls: list[HttpUrl]

    @field_validator("urls", mode="before")
    @classmethod
    def coerce_single_url_to_list(cls, v):
        if isinstance(v, (str, HttpUrl)):
            return [v]
        return v

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
    content: str | None = None
    error: str | None = None


class SingleURLExtractRequest(BaseModel):
    article_pdf_link: HttpUrl

    model_config = {"extra": "allow"}


class SingleURLExtractResult(BaseModel):
    content: str | None = None
    error: str | None = None

    model_config = {"extra": "allow"}


class FileTooLargeError(Exception):
    """Raised when a downloaded file exceeds the size limit."""

    pass


_inflight_tasks: dict[str, asyncio.Future[URLExtractResult]] = {}
_inflight_lock = asyncio.Lock()


async def _download_content_with_retry(
    client: httpx.AsyncClient,
    url: str,
    download_semaphore: asyncio.Semaphore,
) -> tuple[bytes, str | None, str]:
    """Download bytes from URL with retry for transient server/network errors."""
    attempts = max(1, settings.DOWNLOAD_RETRIES)
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            async with download_semaphore:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()

                    # Check Content-Length before reading
                    content_length = int(response.headers.get("content-length", 0))
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
                    content_disposition = response.headers.get("content-disposition", "")
                    return content, content_type, content_disposition

        except FileTooLargeError:
            # File size limit violations should not be retried
            raise
        except httpx.HTTPStatusError as exc:
            # Retry transient server errors (5xx) or rate limits (429)
            if exc.response.status_code >= 500 or exc.response.status_code == 429:
                last_error = exc
                if attempt < attempts:
                    backoff = settings.DOWNLOAD_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                    logger.warning(
                        "Download attempt %d/%d for URL %s failed with status %d; retrying in %.1fs...",
                        attempt,
                        attempts,
                        url,
                        exc.response.status_code,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = exc
            if attempt < attempts:
                backoff = settings.DOWNLOAD_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "Download attempt %d/%d for URL %s failed with %s (%s); retrying in %.1fs...",
                    attempt,
                    attempts,
                    url,
                    type(exc).__name__,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
                continue
            raise

    if last_error:
        raise last_error
    raise RuntimeError(f"Download failed for {url}")


async def _execute_url_extraction(
    url: str,
    client: httpx.AsyncClient,
    executor,
    download_semaphore: asyncio.Semaphore,
    extraction_semaphore: asyncio.Semaphore,
) -> URLExtractResult:
    """Internal runner to download, detect format, and extract text from a single URL."""
    try:
        content, content_type, content_disposition = await _download_content_with_retry(
            client=client,
            url=url,
            download_semaphore=download_semaphore,
        )

        # Detect format, prioritizing Content-Disposition filename if present
        effective_filename = url
        if "filename=" in content_disposition.lower():
            import re

            match = re.search(
                r'filename\*?=(?:UTF-8\'\')?["\']?([^";\r\n]+)',
                content_disposition,
                re.IGNORECASE,
            )
            if match:
                effective_filename = match.group(1).strip()

        # Detect format
        fmt = detect_format(content, filename=effective_filename, content_type=content_type)

        # Extract text with timeout enforcement
        extractor = get_extractor(fmt, executor)
        async with extraction_semaphore:
            text = await asyncio.wait_for(
                extractor.extract(content, filename=url),
                timeout=float(settings.REQUEST_TIMEOUT_SECONDS),
            )
            text = sanitize_surrogates(text)

        # Detect empty extraction
        if not text.strip():
            logger.warning(
                "Extraction yielded no text for URL %s — document may be empty, image-only, or contain unreadable vectorized paths",
                url,
            )
            result = URLExtractResult(
                url=url,
                content=text,
                error="Extraction yielded no text. Document may be empty, image-only, or contain unreadable vectorized paths.",
            )
        else:
            result = URLExtractResult(url=url, content=text, error=None)

        # Store in cache (cache only stores if content is not None and not blank)
        url_cache.set(url, result)
        return result

    except SSRFBlockedError as exc:
        logger.warning("SSRF blocked URL %s during request: %s", url, exc)
        return URLExtractResult(url=url, content=None, error=f"SecurityError: {exc}")
    except TimeoutError:
        logger.warning(
            "Extraction timed out after %ds for URL %s", settings.REQUEST_TIMEOUT_SECONDS, url
        )
        return URLExtractResult(
            url=url,
            content=None,
            error=f"TimeoutError: Extraction exceeded {settings.REQUEST_TIMEOUT_SECONDS}s limit",
        )
    except UnsupportedFormatError as exc:
        logger.warning("Unsupported format for URL %s: %s", url, exc)
        return URLExtractResult(url=url, content=None, error=str(exc))
    except FileTooLargeError as exc:
        logger.warning("File too large for URL %s: %s", url, exc)
        return URLExtractResult(url=url, content=None, error=str(exc))
    except Exception as exc:
        logger.warning("Failed to process URL %s: %s (%s)", url, exc, type(exc).__name__)
        return URLExtractResult(url=url, content=None, error=f"{type(exc).__name__}: {exc}")


async def _process_url(
    url: str,
    client,
    executor,
    download_semaphore: asyncio.Semaphore,
    extraction_semaphore: asyncio.Semaphore,
) -> URLExtractResult:
    """Download and extract text from a single URL with caching and in-flight coalescing."""
    try:
        validate_safe_url(url)
    except SSRFBlockedError as exc:
        logger.warning("SSRF blocked URL %s: %s", url, exc)
        return URLExtractResult(url=url, content=None, error=f"SecurityError: {exc}")

    # Check cache first
    cached_result = url_cache.get(url)
    if cached_result:
        logger.info("Cache hit for URL %s", url)
        return cached_result

    # Coalesce simultaneous in-flight requests for the identical URL
    future: asyncio.Future[URLExtractResult] | None = None
    existing_task: asyncio.Future[URLExtractResult] | None = None
    async with _inflight_lock:
        if url in _inflight_tasks:
            logger.info("Coalescing with active in-flight request for URL %s", url)
            existing_task = _inflight_tasks[url]
        else:
            future = asyncio.get_running_loop().create_future()
            _inflight_tasks[url] = future

    if existing_task is not None:
        return await existing_task

    assert future is not None

    try:
        result = await _execute_url_extraction(
            url, client, executor, download_semaphore, extraction_semaphore
        )
        if not future.done():
            future.set_result(result)
        return result
    except Exception as exc:
        err_res = URLExtractResult(url=url, content=None, error=f"{type(exc).__name__}: {exc}")
        if not future.done():
            future.set_result(err_res)
        return err_res
    finally:
        async with _inflight_lock:
            _inflight_tasks.pop(url, None)


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


@router.post(
    "/article-url",
    response_model=SingleURLExtractResult | list[SingleURLExtractResult],
)
async def extract_article_url(
    body: SingleURLExtractRequest | list[SingleURLExtractRequest],
    request: Request,
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
            extraction_semaphore,
        )
        for item in items
    ]

    results = await asyncio.gather(*tasks)

    formatted_results = []
    for item, r in zip(items, results, strict=False):
        extra = item.model_extra or {}
        formatted_results.append(SingleURLExtractResult(content=r.content, error=r.error, **extra))

    return formatted_results if is_list else formatted_results[0]
