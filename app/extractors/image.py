import asyncio
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import pytesseract

from app.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class ImageExtractor(BaseExtractor):
    """
    Extracts text from images (PNG, JPEG, etc.) using Tesseract OCR.
    """

    def __init__(self, executor: ThreadPoolExecutor):
        self._executor = executor

    async def extract(self, content: bytes, filename: str = "") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self._sync_extract, content
        )

    def _sync_extract(self, content: bytes) -> str:
        try:
            with Image.open(io.BytesIO(content)) as image:
                # Perform OCR using pytesseract
                text = pytesseract.image_to_string(image)
                return text.strip()
        except Exception as e:
            logger.error("Failed to perform OCR: %s", e)
            raise RuntimeError(f"OCR extraction failed: {e}")
