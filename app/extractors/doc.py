from app.extractors.libreoffice_base import LibreOfficeBaseExtractor
from app.extractors.docx import DocxExtractor


class DocExtractor(LibreOfficeBaseExtractor):
    INPUT_SUFFIX = ".doc"
    TARGET_FORMAT = "docx"

    def __init__(self, executor):
        super().__init__(executor)
        self._delegate = DocxExtractor(executor)

    def _sync_extract(self, content: bytes, filename: str = "") -> str:
        converted = self._convert_via_libreoffice(content, self.INPUT_SUFFIX, self.TARGET_FORMAT)
        return self._delegate._sync_extract(converted)
