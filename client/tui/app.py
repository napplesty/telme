"""Telme TUI application - main entry point."""
import asyncio
from typing import Optional

from textual.app import App
from textual.binding import Binding

from client.api.client import APIClient
from client.config import config
from client.crypto.key_manager import KeyManager
from client.services.chat_service import ChatService
from client.services.contact_service import ContactService
from client.storage.database import Database
from client.tui.screens.chat_screen import ChatScreen
from client.utils.logger import get_logger

logger = get_logger(__name__)


class TelmeApp(App):
    """Telme chat application - main entry point.

    This class is responsible for:
    - Initializing all services and infrastructure
    - Managing screen navigation
    - Handling application lifecycle events

    All UI logic is delegated to screens and widgets.
    """

    CSS = """
    /* Global styles */
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self):
        """Initialize the application."""
        super().__init__()
        # Infrastructure components
        self._key_manager: Optional[KeyManager] = None
        self._database: Optional[Database] = None
        self._api_client: Optional[APIClient] = None

        # Service layer
        self._chat_service: Optional[ChatService] = None
        self._contact_service: Optional[ContactService] = None

    @property
    def chat_service(self) -> ChatService:
        """Get the chat service."""
        if self._chat_service is None:
            raise RuntimeError("Chat service not initialized")
        return self._chat_service

    @property
    def contact_service(self) -> ContactService:
        """Get the contact service."""
        if self._contact_service is None:
            raise RuntimeError("Contact service not initialized")
        return self._contact_service

    async def on_mount(self) -> None:
        """Handle application mount event.

        Initializes all services and pushes the main chat screen.
        """
        try:
            await self._initialize_services()
        except Exception as e:
            logger.critical(f"Startup failed: {e}")
            self.exit(message=f"Startup error: {e}")
            return

        logger.info("Services initialized successfully")

        # Push the main chat screen
        self.push_screen(ChatScreen(
            chat_service=self._chat_service,
            contact_service=self._contact_service
        ))

        logger.info("Application mounted, chat screen pushed")

    async def _initialize_services(self) -> None:
        """Initialize all services and infrastructure."""
        # Initialize key manager
        logger.info("Initializing key manager...")
        self._key_manager = KeyManager()
        self._key_manager.get_or_create_keys()
        logger.info(f"Key manager initialized, user_id: {self._key_manager.user_id[:12]}...")

        # Initialize database
        logger.info("Initializing database...")
        self._database = Database(config.DB_PATH)
        logger.info(f"Database initialized at {config.DB_PATH}")

        # Initialize API client
        logger.info("Initializing API client...")
        self._api_client = APIClient()
        logger.info(f"API client initialized, server: {config.SERVER_URL}")

        # Initialize services
        logger.info("Initializing services...")
        self._chat_service = ChatService(
            key_manager=self._key_manager,
            database=self._database,
            api_client=self._api_client
        )

        self._contact_service = ContactService(
            database=self._database,
            api_client=self._api_client
        )

        logger.info("Services initialized")

    async def on_unmount(self) -> None:
        """Handle application unmount event.

        Clean up all resources.
        """
        logger.info("Application unmounting...")

        # Stop message polling
        if self._chat_service:
            await self._chat_service.close()
            logger.info("Chat service closed")

        # Close API client
        if self._api_client:
            await self._api_client.close()
            logger.info("API client closed")

        # Close database
        if self._database:
            self._database.close()
            logger.info("Database closed")

        logger.info("Application unmounted")


def main():
    """Main entry point for the Telme client."""
    app = TelmeApp()
    app.run()


if __name__ == "__main__":
    main()
