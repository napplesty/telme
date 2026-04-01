"""FastAPI application factory."""
import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api import health, keys, messages
from server.config import config
from server.services.key_service import key_service
from server.services.message_service import message_service
from server.utils.logger import get_logger

logger = get_logger(__name__)


async def _cleanup_loop() -> None:
    """Run periodic cleanup for in-memory server state."""
    while True:
        await asyncio.sleep(config.CLEANUP_INTERVAL)
        removed_messages = await message_service.cleanup_expired_messages()
        key_service.cleanup_stale_data()
        if removed_messages:
            logger.info(
                f"Periodic cleanup removed {removed_messages} expired messages"
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown events."""
    # Startup
    key_service.reset()
    message_service.reset()

    logger.info(f"Starting {config.APP_NAME} v{config.VERSION}")
    logger.info(f"Server running on {config.HOST}:{config.PORT}")
    logger.info(f"Message TTL: {config.MESSAGE_TTL} seconds")
    logger.info("Reset in-memory server state for fresh startup")

    cleanup_task = asyncio.create_task(_cleanup_loop())
    app.state.cleanup_task = cleanup_task

    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task

        # Shutdown
        logger.info("Shutting down server")


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title=config.APP_NAME,
        version=config.VERSION,
        description="End-to-end encrypted chat server - message forwarding only",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(health.router)
    app.include_router(keys.router, prefix=config.API_PREFIX)
    app.include_router(messages.router, prefix=config.API_PREFIX)

    logger.info("FastAPI application created")

    return app
