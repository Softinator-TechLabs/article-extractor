import asyncio
import logging
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

from app.extractors.base import BaseExtractor
from app.extractors.pptx import PptxExtractor

logger = logging.getLogger(__name__)


class PptExtractor(BaseExtractor):
    """
    Handles legacy .ppt (binary OLE) files via LibreOffice headless conversion.
    Converts .ppt → .pptx then delegates to PptxExtractor.
    """

    def __init__(self, executor: ThreadPoolExecutor):
        self._executor = executor
        self._pptx_extractor = PptxExtractor(executor)

    async def extract(self, content: bytes, filename: str = "") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self._sync_extract, content, filename
        )

    def _sync_extract(self, content: bytes, filename: str = "") -> str:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, "input.ppt")
            with open(input_path, "wb") as f:
                f.write(content)

            result = subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--norestore",
                    "--nofirststartwizard",
                    "--convert-to", "pptx",
                    "--outdir", tmp_dir,
                    input_path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"LibreOffice .ppt conversion failed: {result.stderr.strip()}"
                )

            output_path = os.path.join(tmp_dir, "input.pptx")
            if not os.path.exists(output_path):
                raise RuntimeError(
                    f"LibreOffice produced no output for {filename}"
                )

            with open(output_path, "rb") as f:
                pptx_bytes = f.read()

        return self._pptx_extractor._sync_extract(pptx_bytes)
