import asyncio
import io
import logging
import zipfile
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree

from app.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class PagesExtractor(BaseExtractor):
    """
    Extracts text from Apple Pages (.pages) files.

    Strategy 1 (post-2013 format): Extract QuickLook/Preview.pdf from the
    zip and pass to PDFExtractor. Highest fidelity.

    Strategy 2 (pre-2013 format): Parse index.xml text nodes directly.

    Strategy 3 (fallback): LibreOffice conversion to docx.
    LibreOffice's .pages support is partial but covers many cases.
    """

    def __init__(self, executor: ThreadPoolExecutor):
        self._executor = executor
        # Lazy imports to avoid circular dependency — set by format_router
        # after all extractors are instantiated
        self._pdf_extractor = None
        self._doc_extractor = None

    async def extract(self, content: bytes, filename: str = "") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._sync_extract, content, filename)

    def _sync_extract(self, content: bytes, filename: str = "") -> str:
        # Strategy 1: PDF preview inside the zip (post-2013 Pages)
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                namelist = z.namelist()

                if "QuickLook/Preview.pdf" in namelist:
                    logger.debug("pages: using QuickLook/Preview.pdf strategy")
                    pdf_bytes = z.read("QuickLook/Preview.pdf")
                    if self._pdf_extractor:
                        return self._pdf_extractor._sync_extract(pdf_bytes, filename)

                # Strategy 2: older XML-based format
                if "index.xml" in namelist:
                    logger.debug("pages: using index.xml strategy")
                    xml_bytes = z.read("index.xml")
                    return self._extract_xml_text(xml_bytes)

        except zipfile.BadZipFile:
            logger.warning("pages: not a valid zip — trying LibreOffice fallback")
        except Exception as e:
            logger.warning("pages: zip extraction failed (%s) — trying LibreOffice fallback", e)

        # Strategy 3: LibreOffice fallback
        logger.debug("pages: falling back to LibreOffice conversion")
        if self._doc_extractor:
            from app.extractors.libreoffice_base import LibreOfficeBaseExtractor
            from app.extractors.docx import DocxExtractor

            class _PagesLOExtractor(LibreOfficeBaseExtractor):
                INPUT_SUFFIX = ".pages"
                TARGET_FORMAT = "docx"

            extractor = _PagesLOExtractor(self._executor)
            extractor._delegate = DocxExtractor(self._executor)
            converted = extractor._convert_via_libreoffice(content, ".pages", "docx")
            return extractor._delegate._sync_extract(converted)

        raise RuntimeError("PagesExtractor: all strategies failed and no fallback available")

    def _extract_xml_text(self, xml_bytes: bytes) -> str:
        """
        Extract text from older Pages index.xml format.
        Strips all tags, joins text nodes with whitespace.
        """
        try:
            root = ElementTree.fromstring(xml_bytes)
            texts = []
            for elem in root.iter():
                if elem.text and elem.text.strip():
                    texts.append(elem.text.strip())
                if elem.tail and elem.tail.strip():
                    texts.append(elem.tail.strip())
            return "\n".join(texts)
        except ElementTree.ParseError as e:
            raise RuntimeError(f"pages: index.xml parse failed: {e}")
