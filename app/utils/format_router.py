from __future__ import annotations

import logging
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import urlparse, unquote

if TYPE_CHECKING:
    from concurrent.futures import ThreadPoolExecutor

from app.extractors.pdf import PDFExtractor
from app.extractors.docx import DocxExtractor
from app.extractors.doc import DocExtractor
from app.extractors.tex import TexExtractor
from app.extractors.rtf import RTFExtractor
from app.extractors.plaintext import PlainTextExtractor

logger = logging.getLogger(__name__)


class UnsupportedFormatError(Exception):
    """Raised when a file format is not supported."""
    pass


# Extension → extractor class mapping
_EXTENSION_MAP: dict[str, type] = {
    ".pdf": PDFExtractor,
    ".docx": DocxExtractor,
    ".doc": DocExtractor,
    ".tex": TexExtractor,
    ".rtf": RTFExtractor,
    ".md": PlainTextExtractor,
    ".markdown": PlainTextExtractor,
    ".txt": PlainTextExtractor,
    ".text": PlainTextExtractor,
}

# MIME type → extractor class mapping (fallback)
_MIME_MAP: dict[str, type] = {
    "application/pdf": PDFExtractor,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocxExtractor,
    "application/msword": DocExtractor,
    "application/rtf": RTFExtractor,
    "text/rtf": RTFExtractor,
    "text/x-tex": TexExtractor,
    "application/x-tex": TexExtractor,
    "application/x-latex": TexExtractor,
    "text/plain": PlainTextExtractor,
    "text/markdown": PlainTextExtractor,
}


def _extract_extension(filename: str | None) -> str | None:
    """Extract lowercase extension from a filename or URL path."""
    if not filename:
        return None
    # Handle URLs
    if filename.startswith(("http://", "https://")):
        parsed = urlparse(filename)
        path = unquote(parsed.path)
    else:
        path = filename
    suffix = PurePosixPath(path).suffix.lower()
    return suffix if suffix else None


def _sniff_magic_bytes(content: bytes, filename: str | None) -> str | None:
    """Detect format by inspecting magic bytes at start of content."""
    if len(content) < 4:
        return None
    # PDF
    if content[:4] == b"%PDF":
        return ".pdf"
    # ZIP-based (could be .docx)
    if content[:4] == b"PK\x03\x04":
        ext = _extract_extension(filename)
        if ext == ".docx":
            return ".docx"
        # Unknown ZIP archive — don't assume
        return None
    # Microsoft OLE Compound File (legacy .doc, .xls, .ppt)
    if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return ".doc"
    return None


def detect_format(
    content: bytes,
    filename: str | None = None,
    content_type: str | None = None,
) -> str:
    """Detect the document format and return the normalised extension string.

    Priority:
    1. Explicit extension from filename
    2. Magic-byte sniffing
    3. MIME type from content_type header
    4. Fallback to plaintext (attempt utf-8 decode)
    """
    # 1. Extension
    ext = _extract_extension(filename)
    if ext and ext in _EXTENSION_MAP:
        return ext

    # 2. Magic bytes
    sniffed = _sniff_magic_bytes(content, filename)
    if sniffed:
        return sniffed

    # 3. MIME type
    if content_type:
        mime = content_type.split(";")[0].strip().lower()
        for mime_key, _ in _MIME_MAP.items():
            if mime == mime_key:
                return next(
                    (e for e, cls in _EXTENSION_MAP.items() if cls == _MIME_MAP[mime_key]),
                    ".txt",
                )

    # 4. Fallback — try plaintext
    return ".txt"


def get_extractor(
    fmt: str,
    executor: "ThreadPoolExecutor",
):
    """Return an instantiated extractor for the given format string."""
    cls = _EXTENSION_MAP.get(fmt)
    if cls is None:
        raise UnsupportedFormatError(f"Unsupported format: {fmt}")
    # PlainTextExtractor doesn't need an executor
    if cls is PlainTextExtractor:
        return cls()
    return cls(executor)
