import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from app.config import settings
from app.dependencies import get_api_key
from app.middleware.security import SecurityHeadersMiddleware
from app.routers import binary_extract, url_extract
from app.utils.cache import url_cache
from app.utils.http_client import close_client, create_client

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup Validation ──
    if settings.is_production and settings.REQUIRE_API_KEY and not settings.API_KEY:
        logger.critical(
            "FATAL: Production mode requires API_KEY to be configured. Set API_KEY or set REQUIRE_API_KEY=false."
        )
        raise RuntimeError("API_KEY must be configured in production environment.")

    # ── Startup ──
    app.state.executor = ThreadPoolExecutor(max_workers=settings.MAX_WORKERS)
    app.state.http_client = await create_client()
    app.state.download_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DOWNLOADS)
    app.state.extraction_semaphore = asyncio.Semaphore(settings.MAX_WORKERS)
    logger.info(
        "Document Extractor started — env=%s, docs=%s, workers=%d, max_downloads=%d, max_file_size=%dMB",
        settings.ENVIRONMENT,
        settings.docs_enabled,
        settings.MAX_WORKERS,
        settings.MAX_CONCURRENT_DOWNLOADS,
        settings.MAX_FILE_SIZE_MB,
    )
    yield
    # ── Shutdown ──
    app.state.executor.shutdown(wait=True, cancel_futures=True)
    await close_client(app.state.http_client)
    logger.info("Document Extractor shut down.")


# OpenAPI & Docs gate: disabled by default in production unless explicitly enabled
docs_url = "/docs" if settings.docs_enabled else None
redoc_url = "/redoc" if settings.docs_enabled else None
openapi_url = "/openapi.json" if settings.docs_enabled else None

app = FastAPI(
    title="Document Extractor",
    description="Extract text content from research papers and manuscripts.",
    version="1.0.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
    lifespan=lifespan,
)

# Defensive Middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Always wire authentication dependency so dynamic API_KEY configuration works seamlessly
router_dependencies = [Depends(get_api_key)]

app.include_router(
    url_extract.router, prefix="/extract", tags=["extract"], dependencies=router_dependencies
)
app.include_router(
    binary_extract.router, prefix="/extract", tags=["extract"], dependencies=router_dependencies
)


@app.get("/")
async def root():
    """Service status banner."""
    return {
        "service": "document-extractor",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/cache", dependencies=router_dependencies)
async def get_cache_stats():
    """Return in-memory cache statistics for this worker process."""
    return url_cache.stats()


@app.delete("/cache", dependencies=router_dependencies)
async def flush_cache():
    """Flush the in-memory URL extraction cache for this worker process."""
    count = url_cache.clear()
    return {"flushed": count, "note": "Cache cleared on active worker"}
