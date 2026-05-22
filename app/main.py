import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.routers import binary_extract, url_extract
from app.utils.http_client import close_client, create_client
from app.dependencies import get_api_key
from fastapi import Depends

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    app.state.executor = ThreadPoolExecutor(max_workers=settings.MAX_WORKERS)
    app.state.http_client = await create_client()
    app.state.download_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DOWNLOADS)
    app.state.extraction_semaphore = asyncio.Semaphore(settings.MAX_WORKERS)
    logger.info(
        "Document Extractor started — workers=%d, max_downloads=%d, max_file_size=%dMB",
        settings.MAX_WORKERS,
        settings.MAX_CONCURRENT_DOWNLOADS,
        settings.MAX_FILE_SIZE_MB,
    )
    yield
    # ── Shutdown ──
    app.state.executor.shutdown(wait=True)
    await close_client(app.state.http_client)
    logger.info("Document Extractor shut down.")


app = FastAPI(
    title="Document Extractor",
    description="Extract text content from research papers and manuscripts.",
    version="1.0.0",
    lifespan=lifespan,
)

# Set up global dependencies if API key is configured
router_dependencies = []
if settings.API_KEY:
    router_dependencies.append(Depends(get_api_key))

app.include_router(url_extract.router, prefix="/extract", tags=["extract"], dependencies=router_dependencies)
app.include_router(binary_extract.router, prefix="/extract", tags=["extract"], dependencies=router_dependencies)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
