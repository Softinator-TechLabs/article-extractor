# Document Extractor

A production-ready FastAPI service for extracting text content from documents (research papers, manuscripts). Designed to be called by n8n workflows.

## Supported Formats

| Format | Engine | Extension(s) |
|--------|--------|--------------|
| PDF | pymupdf4llm | `.pdf` |
| DOCX | python-docx + mammoth (fallback) | `.docx` |
| LaTeX | TexSoup + regex (fallback) | `.tex` |
| RTF | striprtf | `.rtf` |
| Plain Text | built-in decode | `.md`, `.markdown`, `.txt`, `.text` |

## Quick Start

```bash
# Build and run
docker compose up --build

# Health check
curl http://localhost:8000/health
```

## API Endpoints

### `GET /health`

Returns `{"status": "ok"}`.

### `POST /extract/urls`

Extract text from documents at given URLs.

```bash
curl -X POST http://localhost:8000/extract/urls \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com/paper.pdf"]}'
```

**Response:**

```json
[
  {
    "url": "https://example.com/paper.pdf",
    "content": "# Title\n\nExtracted text...",
    "error": null
  }
]
```

### `POST /extract/binary`

Extract text from uploaded binary files (designed for n8n integration).

```bash
curl -X POST http://localhost:8000/extract/binary \
  -F 'data=[{"binaryKey": "file", "fileName": "paper.pdf"}]' \
  -F 'file=@paper.pdf'
```

**Response:**

```json
[
  {
    "binaryKey": "file",
    "fileName": "paper.pdf",
    "text": "Extracted text...",
    "originalBinaryKey": "file",
    "mdBinaryKey": "file_0",
    "mdFileName": "full.md"
  }
]
```

## Configuration

All settings are configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_WORKERS` | `cpu_count * 2` | ThreadPoolExecutor size |
| `MAX_CONCURRENT_DOWNLOADS` | `10` | Max concurrent URL downloads |
| `DOWNLOAD_TIMEOUT_SECONDS` | `30` | HTTP download timeout |
| `MAX_FILE_SIZE_MB` | `50` | Maximum file size allowed |
| `REQUEST_TIMEOUT_SECONDS` | `120` | Overall request timeout |
| `LOG_LEVEL` | `INFO` | Logging level |

## Deployment on Dokploy

1. Push this repository to your Git provider
2. In Dokploy, create a new service pointing to the repository
3. Dokploy will automatically detect the `docker-compose.yml` and build/deploy
4. Set environment variables in Dokploy's UI as needed

## Architecture

- **No files stored on server** — all processing is in-memory (PDF uses temp files that are immediately deleted)
- **No ML/GPU** — pure code-based extraction
- **Concurrent processing** — uses `asyncio.gather` with thread pools for CPU-bound extraction
- **Graceful error handling** — per-item errors never crash the batch; HTTP 200 always returned
