# ── Stage 1: Builder ──
FROM python:3.11-slim AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

# Extract dependencies from pyproject.toml and install them
RUN python3 -c "import tomllib,pathlib;d=tomllib.loads(pathlib.Path('pyproject.toml').read_text());pathlib.Path('requirements.txt').write_text(chr(10).join(d['project']['dependencies']))" && \
    pip install --no-cache-dir --user -r requirements.txt

# ── Stage 2: Runtime ──
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends libreoffice-nogui tesseract-ocr \
    tesseract-ocr-eng tesseract-ocr-spa tesseract-ocr-fra tesseract-ocr-deu \
    tesseract-ocr-ita tesseract-ocr-por tesseract-ocr-rus tesseract-ocr-ara \
    tesseract-ocr-hin tesseract-ocr-chi-sim tesseract-ocr-jpn tesseract-ocr-osd && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create unprivileged system user and group (UID 10001)
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -m -s /bin/bash appuser

# Copy installed packages from builder to appuser
COPY --from=builder /root/.local /home/appuser/.local
RUN chown -R appuser:appuser /home/appuser/.local

WORKDIR /app
COPY --chown=appuser:appuser app/ ./app/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/appuser \
    PATH=/home/appuser/.local/bin:$PATH

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=10)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--timeout-worker-healthcheck", "120", "--proxy-headers", "--forwarded-allow-ips", "*", "--loop", "uvloop", "--http", "httptools"]
