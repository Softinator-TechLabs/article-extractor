import io
import zipfile
import xml.etree.ElementTree as ET
import pytest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import docx
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.extractors.docx import DocxExtractor
from app.extractors.pages import PagesExtractor


def create_mock_docx() -> bytes:
    doc = docx.Document()
    doc.add_heading("Test Heading 1", level=1)
    doc.add_paragraph("This is paragraph 1 inside the document.")
    doc.add_paragraph("This is paragraph 2.")

    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Header A"
    table.cell(0, 1).text = "Header B"
    table.cell(1, 0).text = "Cell A1"
    table.cell(1, 1).text = "Cell B1"

    doc.add_paragraph("Another paragraph after table.")

    stream = io.BytesIO()
    doc.save(stream)
    return stream.getvalue()


def create_docx_with_content_controls() -> bytes:
    doc = docx.Document()
    doc.add_paragraph("Title inside content control")
    doc.add_paragraph("Body outside content control")
    doc.add_paragraph("Reference inside content control")

    stream = io.BytesIO()
    doc.save(stream)

    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ET.register_namespace("w", ns)

    source = zipfile.ZipFile(io.BytesIO(stream.getvalue()))
    document_xml = source.read("word/document.xml")
    root = ET.fromstring(document_xml)
    body = root.find(f"{{{ns}}}body")
    assert body is not None

    paragraph_indexes = [
        i for i, child in enumerate(list(body))
        if child.tag == f"{{{ns}}}p"
    ]

    for child_index in (paragraph_indexes[-1], paragraph_indexes[0]):
        child = list(body)[child_index]
        sdt = ET.Element(f"{{{ns}}}sdt")
        sdt_content = ET.SubElement(sdt, f"{{{ns}}}sdtContent")
        body.remove(child)
        sdt_content.append(child)
        body.insert(child_index, sdt)

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for item in source.infolist():
            data = (
                ET.tostring(root, encoding="utf-8", xml_declaration=True)
                if item.filename == "word/document.xml"
                else source.read(item.filename)
            )
            target.writestr(item, data)

    source.close()
    return output.getvalue()


def create_mock_zip(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zf:
        for filename, data in files.items():
            zf.writestr(filename, data)
    return stream.getvalue()


@pytest.mark.asyncio
async def test_docx_extractor_correctness():
    executor = ThreadPoolExecutor(max_workers=1)
    extractor = DocxExtractor(executor)
    
    content = create_mock_docx()
    text = await extractor.extract(content, filename="test.docx")
    
    assert "# Test Heading 1" in text
    assert "This is paragraph 1 inside the document." in text
    assert "| Header A | Header B |" in text
    assert "| Cell A1 | Cell B1 |" in text
    assert "Another paragraph after table." in text
    executor.shutdown()


@pytest.mark.asyncio
async def test_docx_extractor_reads_content_controls():
    executor = ThreadPoolExecutor(max_workers=1)
    extractor = DocxExtractor(executor)

    content = create_docx_with_content_controls()
    text = await extractor.extract(content, filename="content_controls.docx")

    assert "Title inside content control" in text
    assert "Body outside content control" in text
    assert "Reference inside content control" in text
    assert text.index("Title inside content control") < text.index("Body outside content control")
    assert text.index("Body outside content control") < text.index("Reference inside content control")
    executor.shutdown()


@pytest.mark.asyncio
async def test_pages_extractor_strategy_1_pdf():
    # Test Strategy 1 (post-2013 Pages) - PDF preview inside zip
    executor = ThreadPoolExecutor(max_workers=1)
    extractor = PagesExtractor(executor)
    
    # Mock PDF extractor and its _sync_extract method
    mock_pdf_extractor = MagicMock()
    mock_pdf_extractor._sync_extract.return_value = "Extracted PDF Text from Pages"
    extractor._pdf_extractor = mock_pdf_extractor
    
    # Create pages mock content which is zip containing QuickLook/Preview.pdf
    mock_pdf_bytes = b"%PDF-1.4 mock content"
    content = create_mock_zip({"QuickLook/Preview.pdf": mock_pdf_bytes})
    
    text = await extractor.extract(content, filename="test.pages")
    
    # Assert that signature mismatch does not occur and correct return is got
    assert text == "Extracted PDF Text from Pages"
    mock_pdf_extractor._sync_extract.assert_called_once_with(mock_pdf_bytes)
    executor.shutdown()


@pytest.mark.asyncio
async def test_pages_extractor_strategy_2_xml():
    # Test Strategy 2 (pre-2013 Pages) - index.xml
    executor = ThreadPoolExecutor(max_workers=1)
    extractor = PagesExtractor(executor)
    
    xml_content = b"""<?xml version="1.0" encoding="utf-8"?>
    <index>
      <text>Some text in index.xml</text>
      <tail>Tail text</tail>
    </index>
    """
    content = create_mock_zip({"index.xml": xml_content})
    
    text = await extractor.extract(content, filename="test_old.pages")
    
    # Assert that text was successfully parsed out of XML
    assert "Some text in index.xml" in text
    assert "Tail text" in text
    executor.shutdown()


def test_api_health():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_api_unauthorized_extract():
    # If API_KEY is set, make sure request without header is unauthorized
    if not settings.API_KEY:
        return
        
    with TestClient(app) as client:
        response = client.post("/extract/urls", json={"urls": []})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_image_extractor():
    from app.extractors.image import ImageExtractor
    executor = ThreadPoolExecutor(max_workers=1)
    extractor = ImageExtractor(executor)
    
    with patch("PIL.Image.open") as mock_open, \
         patch("pytesseract.image_to_string") as mock_ocr:
        
        mock_ocr.return_value = "Mocked OCR Text Results"
        
        text = await extractor.extract(b"mock image bytes", filename="test.png")
        
        assert text == "Mocked OCR Text Results"
        mock_open.assert_called_once()
        mock_ocr.assert_called_once()
        
    executor.shutdown()
