"""Client configuration module."""
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class ClientConfig(BaseSettings):
    """Client configuration settings."""

    # Application info
    APP_NAME: str = "Telme Client"
    VERSION: str = "0.1.0"

    # Server configuration
    SERVER_URL: str = "http://localhost:8000"
    API_VERSION: str = "v1"

    # Polling configuration
    POLL_INTERVAL: int = 2  # seconds
    PULL_BATCH_SIZE: int = 100
    MAX_RETRY: int = 3
    RETRY_DELAY: int = 2  # seconds

    # Storage paths
    DATA_DIR: Path = Path.home() / ".telme"
    DB_PATH: Optional[Path] = None
    KEYS_DIR: Optional[Path] = None

    # Message settings
    MAX_MESSAGE_SIZE: int = 1024 * 1024  # 1MB

    model_config = SettingsConfigDict(
        env_prefix="TELME_CLIENT_",
        env_file=".env",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set up paths
        if self.DB_PATH is None:
            self.DB_PATH = self.DATA_DIR / "messages.db"
        if self.KEYS_DIR is None:
            self.KEYS_DIR = self.DATA_DIR / "keys"

        # Ensure directories exist
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.KEYS_DIR.mkdir(parents=True, exist_ok=True)
        # Set restrictive permissions on keys directory
        self.KEYS_DIR.chmod(0o700)

    @property
    def api_base_url(self) -> str:
        """Get the base URL for API requests."""
        return f"{self.SERVER_URL}/api/{self.API_VERSION}"


# Global config instance
config = ClientConfig()
