import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from app.utils.format_router import detect_format, get_extractor, UnsupportedFormatError

logger = logging.getLogger(__name__)

router = APIRouter()


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

    try:
        # Look up the uploaded file by the binary key
        upload_file = form_files.get(binary_key)
        if upload_file is None:
            logger.warning(
                "No uploaded file found for binaryKey=%s (item %d)",
                binary_key,
                index,
            )
            item["text"] = ""
            item["originalBinaryKey"] = binary_key
            item["mdBinaryKey"] = f"file_{index}"
            item["mdFileName"] = "full.md"
            return item

        if not hasattr(upload_file, "read"):
            logger.warning("Item %d field '%s' is not a file.", index, binary_key)
            item["text"] = ""
            return item

        async with extraction_semaphore:
            # Read file content
            content = await upload_file.read()

            # Detect format from filename extension and MIME
            fmt = detect_format(
                content, 
                filename=file_name, 
                content_type=getattr(upload_file, "content_type", None)
            )

            # Extract
            extractor = get_extractor(fmt, executor)
            text = await extractor.extract(content, filename=file_name)

        item["text"] = text

    except UnsupportedFormatError as exc:
        logger.warning("Unsupported format for item %d (%s): %s", index, file_name, exc)
        item["text"] = ""
    except Exception as exc:
        logger.warning(
            "Extraction failed for item %d (%s): %s (%s)",
            index,
            file_name,
            exc,
            type(exc).__name__,
        )
        item["text"] = ""

    # Always add these metadata fields
    item["originalBinaryKey"] = binary_key
    item["mdBinaryKey"] = f"file_{index}"
    item["mdFileName"] = "full.md"
    return item


@router.post("/binary")
async def extract_binary(
    data: str = Form(...),
    request: Request = None,
):
    """Extract text from binary file uploads sent by n8n.

    Receives multipart/form-data with:
    - ``data``: JSON-encoded array of metadata objects
    - One file field per item, keyed by the item's ``binaryKey`` value

    Returns the same metadata array with ``text``, ``originalBinaryKey``,
    ``mdBinaryKey``, and ``mdFileName`` fields added to each item.
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

    return JSONResponse(content=list(results))
