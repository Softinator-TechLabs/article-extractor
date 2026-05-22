from app.extractors.libreoffice_base import LibreOfficeBaseExtractor
from app.extractors.docx import DocxExtractor
from app.extractors.pptx import PptxExtractor
from app.extractors.xlsx import XlsxExtractor  # defined below


class OdtExtractor(LibreOfficeBaseExtractor):
    """OpenDocument Text → docx → DocxExtractor"""
    INPUT_SUFFIX = ".odt"
    TARGET_FORMAT = "docx"
    def __init__(self, executor):
        super().__init__(executor)
        self._delegate = DocxExtractor(executor)
    def _sync_extract(self, content: bytes, filename: str = "") -> str:
        return self._delegate._sync_extract(
            self._convert_via_libreoffice(content, self.INPUT_SUFFIX, self.TARGET_FORMAT)
        )


class OdpExtractor(LibreOfficeBaseExtractor):
    """OpenDocument Presentation → pptx → PptxExtractor"""
    INPUT_SUFFIX = ".odp"
    TARGET_FORMAT = "pptx"
    def __init__(self, executor):
        super().__init__(executor)
        self._delegate = PptxExtractor(executor)
    def _sync_extract(self, content: bytes, filename: str = "") -> str:
        return self._delegate._sync_extract(
            self._convert_via_libreoffice(content, self.INPUT_SUFFIX, self.TARGET_FORMAT)
        )


class OdsExtractor(LibreOfficeBaseExtractor):
    """OpenDocument Spreadsheet → xlsx → XlsxExtractor"""
    INPUT_SUFFIX = ".ods"
    TARGET_FORMAT = "xlsx"
    def __init__(self, executor):
        super().__init__(executor)
        self._delegate = XlsxExtractor(executor)
    def _sync_extract(self, content: bytes, filename: str = "") -> str:
        return self._delegate._sync_extract(
            self._convert_via_libreoffice(content, self.INPUT_SUFFIX, self.TARGET_FORMAT)
        )


class XlsExtractor(LibreOfficeBaseExtractor):
    """Legacy binary Excel → xlsx → XlsxExtractor"""
    INPUT_SUFFIX = ".xls"
    TARGET_FORMAT = "xlsx"
    def __init__(self, executor):
        super().__init__(executor)
        self._delegate = XlsxExtractor(executor)
    def _sync_extract(self, content: bytes, filename: str = "") -> str:
        return self._delegate._sync_extract(
            self._convert_via_libreoffice(content, self.INPUT_SUFFIX, self.TARGET_FORMAT)
        )


class EpubExtractor(LibreOfficeBaseExtractor):
    """EPUB → convert to txt via LibreOffice"""
    INPUT_SUFFIX = ".epub"
    TARGET_FORMAT = "txt"
    def __init__(self, executor):
        super().__init__(executor)
    def _sync_extract(self, content: bytes, filename: str = "") -> str:
        txt_bytes = self._convert_via_libreoffice(content, self.INPUT_SUFFIX, self.TARGET_FORMAT)
        return txt_bytes.decode("utf-8", errors="replace").strip()


class NumbersExtractor(LibreOfficeBaseExtractor):
    """Apple Numbers → xlsx → XlsxExtractor (LibreOffice has partial support)"""
    INPUT_SUFFIX = ".numbers"
    TARGET_FORMAT = "xlsx"
    def __init__(self, executor):
        super().__init__(executor)
        self._delegate = XlsxExtractor(executor)
    def _sync_extract(self, content: bytes, filename: str = "") -> str:
        return self._delegate._sync_extract(
            self._convert_via_libreoffice(content, self.INPUT_SUFFIX, self.TARGET_FORMAT)
        )


class KeynoteExtractor(LibreOfficeBaseExtractor):
    """Apple Keynote → pptx → PptxExtractor (LibreOffice has partial support)"""
    INPUT_SUFFIX = ".key"
    TARGET_FORMAT = "pptx"
    def __init__(self, executor):
        super().__init__(executor)
        self._delegate = PptxExtractor(executor)
    def _sync_extract(self, content: bytes, filename: str = "") -> str:
        return self._delegate._sync_extract(
            self._convert_via_libreoffice(content, self.INPUT_SUFFIX, self.TARGET_FORMAT)
        )
