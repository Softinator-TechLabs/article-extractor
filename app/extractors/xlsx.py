import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import openpyxl

from app.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class XlsxExtractor(BaseExtractor):
    """
    Extracts text from .xlsx files using openpyxl.
    Iterates all sheets, renders each row as pipe-separated values.
    Skips fully-empty rows. Uses data_only=True to read computed cell values.
    """

    def __init__(self, executor: ThreadPoolExecutor):
        self._executor = executor

    async def extract(self, content: bytes, filename: str = "") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._sync_extract, content)

    def _sync_extract(self, content: bytes) -> str:
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True, read_only=True)
        sheet_sections = []

        for sheet in wb.worksheets:
            rows_text = [f"## Sheet: {sheet.title}"]
            for row in sheet.iter_rows(values_only=True):
                # Skip fully-empty rows
                if all(cell is None for cell in row):
                    continue
                cells = [str(cell).strip() if cell is not None else "" for cell in row]
                rows_text.append(" | ".join(cells))
            if len(rows_text) > 1:  # has at least one data row
                sheet_sections.append("\n".join(rows_text))

        wb.close()
        return "\n\n".join(sheet_sections)
