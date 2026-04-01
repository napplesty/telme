"""Server configuration module."""
from typing import Dict

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseSettings):
    """Server configuration settings."""

    # Application info
    APP_NAME: str = "Telme Server"
    VERSION: str = "0.1.0"

    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # Security configuration
    MAX_MESSAGE_SIZE: int = 1024 * 1024  # 1MB
    MESSAGE_TTL: int = 300  # 5 minutes (in seconds)
    TIMESTAMP_TOLERANCE: int = 300  # 5 minutes (in seconds)
    CLEANUP_INTERVAL: int = 30  # seconds

    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100  # requests per minute
    RATE_LIMIT_PERIOD: int = 60  # seconds

    # API configuration
    API_VERSION: str = "v1"
    API_PREFIX: str = "/api/v1"

    model_config = SettingsConfigDict(
        env_prefix="TELME_SERVER_",
        env_file=".env",
    )

    @property
    def uvicorn_settings(self) -> Dict[str, int]:
        """Get Uvicorn worker settings."""
        return {
            "limit_concurrency": 1000,
            "backlog": 2048,
        }


# Global config instance
config = ServerConfig()
