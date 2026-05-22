import asyncio
import logging
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

from app.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class LibreOfficeBaseExtractor(BaseExtractor):
    """
    Base class for extractors that convert via LibreOffice headless,
    then delegate to another extractor for the converted format.
    
    Subclasses set INPUT_SUFFIX and TARGET_FORMAT, and provide
    a delegate extractor instance.
    """

    INPUT_SUFFIX: str   # e.g. ".doc"
    TARGET_FORMAT: str  # e.g. "docx"

    def __init__(self, executor: ThreadPoolExecutor):
        self._executor = executor

    async def extract(self, content: bytes, filename: str = "") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self._sync_extract, content, filename
        )

    def _convert_via_libreoffice(
        self, content: bytes, input_suffix: str, target_format: str
    ) -> bytes:
        """
        Write content to a temp file, convert via LibreOffice headless,
        return the converted file's bytes. Cleans up temp dir on exit.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, f"input{input_suffix}")
            with open(input_path, "wb") as f:
                f.write(content)

            result = subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--norestore",
                    "--nofirststartwizard",
                    "--convert-to", target_format,
                    "--outdir", tmp_dir,
                    input_path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"LibreOffice conversion ({input_suffix} → {target_format}) failed: "
                    f"{result.stderr.strip()}"
                )

            output_path = os.path.join(tmp_dir, f"input.{target_format}")
            if not os.path.exists(output_path):
                raise RuntimeError(
                    f"LibreOffice produced no output file "
                    f"(expected input.{target_format})"
                )

            with open(output_path, "rb") as f:
                return f.read()

    def _sync_extract(self, content: bytes, filename: str = "") -> str:
        raise NotImplementedError
