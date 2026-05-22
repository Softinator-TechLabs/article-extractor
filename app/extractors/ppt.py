from app.extractors.libreoffice_base import LibreOfficeBaseExtractor
from app.extractors.pptx import PptxExtractor


class PptExtractor(LibreOfficeBaseExtractor):
    INPUT_SUFFIX = ".ppt"
    TARGET_FORMAT = "pptx"

    def __init__(self, executor):
        super().__init__(executor)
        self._delegate = PptxExtractor(executor)

    def _sync_extract(self, content: bytes, filename: str = "") -> str:
        converted = self._convert_via_libreoffice(content, self.INPUT_SUFFIX, self.TARGET_FORMAT)
        return self._delegate._sync_extract(converted)
