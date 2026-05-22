import asyncio
import io
import logging
from concurrent.futures import ThreadPoolExecutor

import docx
import mammoth

from app.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class DocxExtractor(BaseExtractor):
    """Extract text from .docx documents.

    Primary: python-docx for structured extraction with heading preservation.
    Fallback: mammoth raw text extraction.
    """

    def __init__(self, executor: ThreadPoolExecutor) -> None:
        self._executor = executor

    async def extract(self, content: bytes, filename: str = "") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._sync_extract, content, filename)

    def _sync_extract(self, content: bytes, filename: str) -> str:
        try:
            return self._extract_with_python_docx(content)
        except Exception as exc:
            logger.warning(
                "python-docx failed for %s (%s), falling back to mammoth",
                filename,
                type(exc).__name__,
            )
            return self._extract_with_mammoth(content)

    def _extract_with_python_docx(self, content: bytes) -> str:
        doc = docx.Document(io.BytesIO(content))
        parts: list[str] = []

        for element in doc.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if tag == "p":
                # Find the matching Paragraph object
                for para in doc.paragraphs:
                    if para._element is element:
                        parts.append(self._format_paragraph(para))
                        break
            elif tag == "tbl":
                for table in doc.tables:
                    if table._element is element:
                        parts.append(self._format_table(table))
                        break

        return "\n\n".join(p for p in parts if p.strip())

    @staticmethod
    def _format_paragraph(para) -> str:
        style_name = (para.style.name or "").lower() if para.style else ""
        text = para.text.strip()
        if not text:
            return ""

        heading_map = {
            "heading 1": "# ",
            "heading 2": "## ",
            "heading 3": "### ",
            "heading 4": "#### ",
            "heading 5": "##### ",
            "heading 6": "###### ",
            "title": "# ",
            "subtitle": "## ",
        }

        prefix = heading_map.get(style_name, "")
        return f"{prefix}{text}"

    @staticmethod
    def _format_table(table) -> str:
        rows: list[list[str]] = []
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            rows.append(cells)

        if not rows:
            return ""

        lines: list[str] = []
        # Header row
        lines.append("| " + " | ".join(rows[0]) + " |")
        lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
        # Data rows
        for row in rows[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    @staticmethod
    def _extract_with_mammoth(content: bytes) -> str:
        result = mammoth.extract_raw_text(io.BytesIO(content))
        return result.value
