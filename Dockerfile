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
    apt-get install -y --no-install-recommends antiword && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

WORKDIR /app
COPY app/ ./app/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--loop", "uvloop", "--http", "httptools"]
