import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import fitz
import pymupdf4llm

from app.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class PDFExtractor(BaseExtractor):
    """Extract text from PDF documents using pymupdf4llm."""

    def __init__(self, executor: ThreadPoolExecutor) -> None:
        self._executor = executor

    async def extract(self, content: bytes, filename: str = "") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._sync_extract, content)

    @staticmethod
    def _sync_extract(content: bytes) -> str:
        # Optimization: Parse the PDF entirely in memory instead of using temporary files on disk
        with fitz.open(stream=content, filetype="pdf") as doc:
            return pymupdf4llm.to_markdown(doc)
