import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from striprtf.striprtf import rtf_to_text

from app.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class RTFExtractor(BaseExtractor):
    """Extract text from RTF documents using striprtf."""

    def __init__(self, executor: ThreadPoolExecutor) -> None:
        self._executor = executor

    async def extract(self, content: bytes, filename: str = "") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._sync_extract, content)

    @staticmethod
    def _sync_extract(content: bytes) -> str:
        # RTF spec uses latin-1 encoding; try that first, then utf-8 fallback
        for encoding in ("latin-1", "utf-8"):
            try:
                text = content.decode(encoding)
                return rtf_to_text(text)
            except (UnicodeDecodeError, Exception):
                continue
        # Last resort: decode with errors replaced
        text = content.decode("latin-1", errors="replace")
        return rtf_to_text(text)
