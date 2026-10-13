import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.utils.format_router import UnsupportedFormatError, detect_format, get_extractor
from app.utils.sanitizer import sanitize_obj, sanitize_surrogates

logger = logging.getLogger(__name__)

router = APIRouter()


class FileTooLargeError(Exception):
    """Raised when an uploaded file exceeds the size limit."""

    pass


async def _extract_item(
    item: dict[str, Any],
    form_files: dict,
    index: int,
    executor,
    extraction_semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Process a single item from the binary extraction request."""
    binary_key = item.get("binaryKey", "")
    file_name = item.get("fileName", "")
    text = ""

    if "n8n_meta" in item and isinstance(item["n8n_meta"], dict):
        return_item = item["n8n_meta"]
    else:
        return_item = item

    try:
        # Look up the uploaded file by the binary key
        upload_file = form_files.get(binary_key)
        if upload_file is None:
            logger.warning(
                "No uploaded file found for binaryKey=%s (item %d)",
                binary_key,
                index,
            )
            return_item["text"] = text
            return_item["error"] = f"No uploaded file found for binaryKey: {binary_key}"
            return return_item

        if not hasattr(upload_file, "read"):
            logger.warning("Item %d field '%s' is not a file.", index, binary_key)
            return_item["text"] = text
            return_item["error"] = f"Field '{binary_key}' is not a file"
            return return_item

        if not file_name and getattr(upload_file, "filename", None):
            file_name = upload_file.filename

        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024

        async with extraction_semaphore:
            # Read file content (rewind pointer first if previously read)
            if hasattr(upload_file, "seek"):
                await upload_file.seek(0)
            content = await upload_file.read()
            if len(content) > max_bytes:
                raise FileTooLargeError(
                    f"File too large: {len(content)} bytes (limit: {settings.MAX_FILE_SIZE_MB} MB)"
                )

            # Detect format from filename extension and MIME
            fmt = detect_format(
                content, filename=file_name, content_type=getattr(upload_file, "content_type", None)
            )

            # Extract with timeout enforcement
            extractor = get_extractor(fmt, executor)
            text = await asyncio.wait_for(
                extractor.extract(content, filename=file_name),
                timeout=float(settings.REQUEST_TIMEOUT_SECONDS),
            )
            text = sanitize_surrogates(text)

        if not text.strip():
            return_item["error"] = (
                "Extraction yielded no text. Document may be empty, image-only, or contain unreadable vectorized paths."
            )

    except TimeoutError:
        logger.warning(
            "Extraction timed out after %ds for item %d (%s)",
            settings.REQUEST_TIMEOUT_SECONDS,
            index,
            file_name,
        )
        return_item["error"] = (
            f"TimeoutError: Extraction exceeded {settings.REQUEST_TIMEOUT_SECONDS}s limit"
        )
    except FileTooLargeError as exc:
        logger.warning("File too large for item %d (%s): %s", index, file_name, exc)
        return_item["error"] = str(exc)
    except UnsupportedFormatError as exc:
        logger.warning("Unsupported format for item %d (%s): %s", index, file_name, exc)
        return_item["error"] = str(exc)
    except Exception as exc:
        logger.warning(
            "Extraction failed for item %d (%s): %s (%s)",
            index,
            file_name,
            exc,
            type(exc).__name__,
        )
        return_item["error"] = f"{type(exc).__name__}: {exc}"

    return_item["text"] = sanitize_surrogates(text)
    return return_item


@router.post("/binary")
async def extract_binary(
    request: Request,
    data: str = Form(...),
):
    """Extract text from binary file uploads sent by n8n.

    Receives multipart/form-data with:
    - ``data``: JSON-encoded array of metadata objects
    - One file field per item, keyed by the item's ``binaryKey`` value

    Returns the same metadata array with ``text`` added to each item.
    """
    executor = request.app.state.executor

    # Parse metadata
    try:
        items: list[dict[str, Any]] = json.loads(data)
        if not isinstance(items, list):
            raise TypeError("Root element is not a JSON array")
    except (json.JSONDecodeError, TypeError) as exc:
        return JSONResponse(
            status_code=422,
            content={"detail": f"Invalid JSON array in 'data' field: {exc}"},
        )

    extraction_semaphore = request.app.state.extraction_semaphore

    # Gather uploaded files from form (exclude 'data' field)
    form = await request.form()
    form_files = {key: form[key] for key in form if key != "data"}

    # Process all items concurrently (limited by extraction_semaphore inside _extract_item)
    tasks = [
        _extract_item(item, form_files, i, executor, extraction_semaphore)
        for i, item in enumerate(items)
    ]
    results = await asyncio.gather(*tasks)

    return JSONResponse(content=sanitize_obj(list(results)))
