import asyncio
import logging
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

from app.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class DocExtractor(BaseExtractor):
    """Extract text from legacy .doc (Word 97-2003) documents using antiword.

    Requires 'antiword' to be installed on the system.
    """

    def __init__(self, executor: ThreadPoolExecutor) -> None:
        self._executor = executor

    async def extract(self, content: bytes, filename: str = "") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._sync_extract, content, filename)

    def _sync_extract(self, content: bytes, filename: str) -> str:
        with tempfile.NamedTemporaryFile(suffix=".doc") as tmp:
            tmp.write(content)
            tmp.flush()

            try:
                # Run antiword with UTF-8 mapping
                result = subprocess.run(
                    ["antiword", "-m", "UTF-8", tmp.name],
                    capture_output=True,
                    check=True,
                    text=True,
                    timeout=30,
                )
                return result.stdout.strip()
            except subprocess.TimeoutExpired:
                logger.error("Antiword timed out extracting %s", filename)
                return ""
            except subprocess.CalledProcessError as exc:
                logger.warning(
                    "Antiword failed for %s with exit code %s: %s",
                    filename,
                    exc.returncode,
                    exc.stderr.strip() if exc.stderr else exc.stdout.strip()
                )
                return ""
            except FileNotFoundError:
                logger.error("antiword binary not found. Please install it.")
                return ""
