import asyncio
import csv
import io
from concurrent.futures import ThreadPoolExecutor

from app.extractors.base import BaseExtractor


class CsvExtractor(BaseExtractor):
    """
    Extracts text from .csv files using stdlib csv.
    Renders each row as pipe-separated values, same format as XlsxExtractor.
    """

    def __init__(self, executor: ThreadPoolExecutor):
        self._executor = executor

    async def extract(self, content: bytes, filename: str = "") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._sync_extract, content)

    def _sync_extract(self, content: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = content.decode("utf-8", errors="replace")

        reader = csv.reader(io.StringIO(text))
        rows = []
        for row in reader:
            if any(cell.strip() for cell in row):
                rows.append(" | ".join(cell.strip() for cell in row))
        return "\n".join(rows)
