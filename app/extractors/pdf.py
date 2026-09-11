import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import pymupdf
import pymupdf4llm

from app.config import settings
from app.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class PDFExtractor(BaseExtractor):
    """Extract text from PDF documents using pymupdf4llm with smart OCR fallback."""

    def __init__(self, executor: ThreadPoolExecutor) -> None:
        self._executor = executor

    async def extract(self, content: bytes, filename: str = "") -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._sync_extract, content)

    @staticmethod
    def _sync_extract(content: bytes) -> str:
        # Optimization: Parse the PDF entirely in memory
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            if doc.is_encrypted:
                raise ValueError("PDF document is encrypted / password-protected")

            if len(doc) == 0:
                return ""

            # Pass 1: Fast native text extraction (no OCR)
            text = pymupdf4llm.to_markdown(doc, use_ocr=False)

            if not settings.ENABLE_OCR_FALLBACK:
                return text

            page_count = max(len(doc), 1)
            non_ws_chars = len("".join(text.split()))
            avg_chars = non_ws_chars / page_count

            if avg_chars < settings.OCR_CHARS_PER_PAGE_THRESHOLD:
                logger.info(
                    "PDF native extraction: %.1f non-whitespace chars/page (threshold %d) — triggering OCR fallback",
                    avg_chars,
                    settings.OCR_CHARS_PER_PAGE_THRESHOLD,
                )
                try:
                    ocr_text = pymupdf4llm.to_markdown(
                        doc,
                        use_ocr=True,
                        ocr_language=settings.OCR_LANGUAGE,
                    )
                    # Use OCR output if it produced more meaningful text
                    if len("".join(ocr_text.split())) > non_ws_chars:
                        text = ocr_text
                except Exception as ocr_err:
                    logger.warning("PDF OCR fallback failed: %s. Returning native text.", ocr_err)

            return text
