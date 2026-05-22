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
from app.extractors.pptx import PptxExtractor
from app.extractors.ppt import PptExtractor
from app.extractors.tex import TexExtractor
from app.extractors.rtf import RTFExtractor
from app.extractors.plaintext import PlainTextExtractor

from app.extractors.xlsx import XlsxExtractor
from app.extractors.html import HtmlExtractor
from app.extractors.csv import CsvExtractor
from app.extractors.pages import PagesExtractor

from app.extractors.libreoffice_formats import (
    OdtExtractor, OdpExtractor, OdsExtractor,
    XlsExtractor, EpubExtractor, NumbersExtractor, KeynoteExtractor
)

logger = logging.getLogger(__name__)


class UnsupportedFormatError(Exception):
    """Raised when a file format is not supported."""
    pass


_EXTENSION_MAP: dict[str, type] = {
    # PDF
    ".pdf":      PDFExtractor,

    # Microsoft Office (modern XML)
    ".docx":     DocxExtractor,
    ".pptx":     PptxExtractor,
    ".xlsx":     XlsxExtractor,

    # Microsoft Office (legacy binary OLE2)
    ".doc":      DocExtractor,
    ".ppt":      PptExtractor,
    ".xls":      XlsExtractor,

    # OpenDocument
    ".odt":      OdtExtractor,
    ".odp":      OdpExtractor,
    ".ods":      OdsExtractor,

    # Apple iWork
    ".pages":    PagesExtractor,
    ".numbers":  NumbersExtractor,
    ".key":      KeynoteExtractor,

    # Markup / text
    ".tex":      TexExtractor,
    ".rtf":      RTFExtractor,
    ".html":     HtmlExtractor,
    ".htm":      HtmlExtractor,
    ".xml":      HtmlExtractor,   # reuse tag-stripping logic
    ".md":       PlainTextExtractor,
    ".markdown": PlainTextExtractor,
    ".txt":      PlainTextExtractor,
    ".text":     PlainTextExtractor,
    ".log":      PlainTextExtractor,

    # Data
    ".csv":      CsvExtractor,
    ".tsv":      CsvExtractor,

    # E-book
    ".epub":     EpubExtractor,
}


# Signatures for format sniffing when extension is absent or wrong
PDF_MAGIC    = b"%PDF"
OLE2_MAGIC   = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC    = b"PK\x03\x04"

# ZIP-based formats: inspect internal structure to disambiguate
ZIP_INTERNAL_SIGNATURES = {
    "word/document.xml":      ".docx",
    "ppt/presentation.xml":   ".pptx",
    "xl/workbook.xml":        ".xlsx",
    "index.xml":              ".pages",    # older Pages
    "QuickLook/Preview.pdf":  ".pages",    # newer Pages
    "mimetype":               None,        # check content: epub
    "index.numbers":          ".numbers",
    "index.apxl":             ".key",
    "content.xml":            ".odt",      # ODF family
}


def detect_format_from_bytes(content: bytes, filename: str = "") -> str:
    """
    Returns the canonical extension (e.g. ".pdf") for the content.
    Priority: magic bytes > filename extension.
    """
    header = content[:8]

    if content[:4] == PDF_MAGIC:
        return ".pdf"

    if header == OLE2_MAGIC:
        # OLE2: .doc, .ppt, or .xls — use filename extension to pick
        ext = _ext(filename)
        if ext in (".ppt",):
            return ".ppt"
        if ext in (".xls",):
            return ".xls"
        return ".doc"  # default OLE2 to .doc

    if content[:4] == ZIP_MAGIC:
        # ZIP-based: inspect contents
        try:
            import io as _io
            import zipfile as _zf
            with _zf.ZipFile(_io.BytesIO(content)) as z:
                names = set(z.namelist())
                for internal_path, ext in ZIP_INTERNAL_SIGNATURES.items():
                    if internal_path in names:
                        if internal_path == "mimetype":
                            # EPUB check
                            mt = z.read("mimetype").strip()
                            if b"epub" in mt:
                                return ".epub"
                            continue
                        if internal_path == "content.xml":
                            # ODF family: check relationships
                            if "word/document.xml" not in names:
                                fn_ext = _ext(filename)
                                if fn_ext in (".odp",):
                                    return ".odp"
                                if fn_ext in (".ods",):
                                    return ".ods"
                                return ".odt"
                        return ext
        except Exception:
            pass
        # ZIP but unrecognised internals: fall back to filename extension
        return _ext(filename) or ".docx"

    # No magic match: use filename extension
    ext = _ext(filename)
    if ext:
        return ext

    # Last resort: try to decode as plain text
    try:
        content[:512].decode("utf-8")
        return ".txt"
    except UnicodeDecodeError:
        raise UnsupportedFormatError(f"Cannot determine format for '{filename}'")


def _ext(filename: str) -> str:
    """Lowercase extension including the dot, e.g. '.pdf'. Empty string if none."""
    if not filename:
        return ""
    # Handle URLs
    if filename.startswith(("http://", "https://")):
        parsed = urlparse(filename)
        path = unquote(parsed.path)
    else:
        path = filename
    import os
    return os.path.splitext(path)[1].lower()


def detect_format(
    content: bytes,
    filename: str | None = None,
    content_type: str | None = None,
) -> str:
    """Detect the document format and return the normalised extension string.
    Adapter for the new robust detect_format_from_bytes.
    """
    return detect_format_from_bytes(content, filename or "")


# Global dictionary holding singleton extractors to avoid reinitialization overhead
_extractor_instances = {}


def get_extractor(
    fmt: str,
    executor: "ThreadPoolExecutor",
):
    """Return an instantiated extractor for the given format string."""
    cls = _EXTENSION_MAP.get(fmt)
    if cls is None:
        raise UnsupportedFormatError(f"Unsupported format: {fmt}")
        
    # Return from cache if already instantiated
    if cls in _extractor_instances:
        return _extractor_instances[cls]

    # Instantiate
    if cls in (PlainTextExtractor, HtmlExtractor, CsvExtractor):
        instance = cls(executor) # although some don't need executor, we pass it for consistency as per base class
    else:
        instance = cls(executor)

    # Post-initialization wiring for PagesExtractor
    if isinstance(instance, PagesExtractor):
        instance._pdf_extractor = get_extractor(".pdf", executor)
        instance._doc_extractor = True  # signal that LO is available

    _extractor_instances[cls] = instance
    return instance
