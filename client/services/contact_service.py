"""Contact service for managing contacts."""
from typing import List, Optional

from client.api.client import APIClient
from client.crypto.key_manager import KeyManager
from client.storage.database import Database
from client.storage.models import Contact
from client.utils.logger import get_logger

logger = get_logger(__name__)


class ContactService:
    """Service for contact management operations."""

    def __init__(self, database: Database, api_client: APIClient):
        """Initialize contact service.

        Args:
            database: Database for contact storage.
            api_client: API client for server communication.
        """
        self.database = database
        self.api_client = api_client

    def add_contact(self, public_key_b64: str, alias: str) -> Contact:
        """Add a new contact.

        Args:
            public_key_b64: Base64-encoded public key.
            alias: User-defined alias for the contact.

        Returns:
            The created Contact object.

        Raises:
            ValueError: If public key is invalid or contact already exists.
        """
        # Validate public key format
        public_key = KeyManager.base64_to_public_key(public_key_b64)

        # Calculate user_id from public key
        user_id = KeyManager.user_id_from_public_key(public_key)

        # Check if contact already exists
        existing = self.database.get_contact(user_id)
        if existing:
            raise ValueError(f"Contact already exists: {existing.alias}")

        # Add to database
        contact = self.database.add_contact(user_id, public_key_b64, alias)

        logger.info(f"Added contact: {alias} ({user_id[:8]}...)")
        return contact

    def get_contact(self, user_id: str) -> Optional[Contact]:
        """Get a contact by user ID.

        Args:
            user_id: The contact's user ID.

        Returns:
            Contact object or None if not found.
        """
        return self.database.get_contact(user_id)

    def get_contact_by_alias(self, alias: str) -> Optional[Contact]:
        """Get a contact by alias.

        Args:
            alias: The contact's alias.

        Returns:
            Contact object or None if not found.
        """
        return self.database.get_contact_by_alias(alias)

    def get_all_contacts(self) -> List[Contact]:
        """Get all contacts.

        Returns:
            List of all contacts.
        """
        return self.database.get_all_contacts()

    def update_alias(self, user_id: str, new_alias: str) -> bool:
        """Update a contact's alias.

        Args:
            user_id: The contact's user ID.
            new_alias: The new alias.

        Returns:
            True if updated, False if contact not found.
        """
        return self.database.update_contact_alias(user_id, new_alias)

    def delete_contact(self, user_id: str) -> bool:
        """Delete a contact.

        Args:
            user_id: The contact's user ID.

        Returns:
            True if deleted, False if not found.
        """
        return self.database.delete_contact(user_id)

    async def fetch_public_key(self, user_id: str) -> Optional[str]:
        """Fetch a user's public key from the server.

        Args:
            user_id: The user's ID.

        Returns:
            Base64-encoded public key or None if not found.
        """
        response = await self.api_client.get(f"/keys/{user_id}")
        return response.get("public_key")
