"""Server entry point."""
import uvicorn

from server.app import create_app
from server.config import config
from server.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Run the server."""
    app = create_app()

    logger.info(f"Starting server on {config.HOST}:{config.PORT}")

    uvicorn.run(
        "server.app:create_app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
        factory=True,
        **config.uvicorn_settings
    )


if __name__ == "__main__":
    main()
