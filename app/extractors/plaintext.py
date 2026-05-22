import logging

from app.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class PlainTextExtractor(BaseExtractor):
    """Extract text from plain text files.

    Tries multiple encodings in priority order.
    Fast enough to run inline without a thread pool.
    """

    _ENCODINGS = ("utf-8", "utf-8-sig", "latin-1", "cp1252")

    async def extract(self, content: bytes, filename: str = "") -> str:
        for encoding in self._ENCODINGS:
            try:
                return content.decode(encoding)
            except (UnicodeDecodeError, ValueError):
                continue
        # Should not reach here since latin-1 accepts all byte values,
        # but guard anyway.
        return content.decode("latin-1", errors="replace")
