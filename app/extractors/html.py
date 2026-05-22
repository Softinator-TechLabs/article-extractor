import asyncio
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

from app.extractors.base import BaseExtractor

SKIP_TAGS = {"script", "style", "head", "meta", "link", "noscript"}


class _TextExtractParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth: int = 0
        self._current_skip_tag: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        # Add line break after block elements
        if tag in {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                   "li", "tr", "br", "section", "article"}:
            self._parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped + " ")

    def get_text(self) -> str:
        raw = "".join(self._parts)
        # Collapse multiple blank lines into one
        import re
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


class HtmlExtractor(BaseExtractor):
    """Extracts text from .html/.htm files using stdlib html.parser. No deps."""

    def __init__(self, executor: ThreadPoolExecutor):
        self._executor = executor

    async def extract(self, content: bytes, filename: str = "") -> str:
        # HTML parsing is fast enough; still run in executor to not block
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._sync_extract, content)

    def _sync_extract(self, content: bytes) -> str:
        # Try common encodings
        for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = content.decode("utf-8", errors="replace")

        parser = _TextExtractParser()
        parser.feed(text)
        return parser.get_text()
