"""Chat service for message handling, encryption, and polling."""
import asyncio
import base64
from datetime import datetime
from typing import Callable, List, Optional

from client.api.client import APIClient
from client.api.messaging import MessagingClient
from client.crypto.encryption import EncryptionManager
from client.crypto.key_manager import KeyManager
from client.crypto.signature import SignatureManager
from client.storage.database import Database
from client.storage.models import Contact, Message, MessageStatus
from client.utils.logger import get_logger

logger = get_logger(__name__)


class ChatService:
    """Service for chat operations including encryption, decryption, and polling."""

    def __init__(
        self,
        key_manager: KeyManager,
        database: Database,
        api_client: APIClient,
    ):
        """Initialize chat service.

        Args:
            key_manager: Key manager for cryptographic operations.
            database: Database for message storage.
            api_client: API client for server communication.
        """
        self.key_manager = key_manager
        self.database = database
        self.api_client = api_client
        self.messaging_client = MessagingClient(api_client, database)
        self._polling = False
        self._on_message_callback: Optional[Callable[[Message, str], None]] = None

    @property
    def user_id(self) -> str:
        """Get current user's ID."""
        return self.key_manager.user_id

    async def send_message(self, recipient: Contact, plaintext: str) -> Message:
        """Send an encrypted message to a contact.

        Args:
            recipient: The contact to send the message to.
            plaintext: The plain text message to send.

        Returns:
            The sent Message object.
        """
        # Get recipient's public key
        recipient_public_key = KeyManager.base64_to_public_key(recipient.public_key)
        recipient_curve25519 = EncryptionManager.convert_ed25519_to_curve25519(
            recipient_public_key
        )

        # Get sender's private key
        sender_signing_key = self.key_manager.signing_key
        sender_private_key = sender_signing_key.to_curve25519_private_key()

        # Encrypt message
        encrypted_b64, nonce_b64 = EncryptionManager.encrypt_to_base64(
            plaintext, sender_private_key, recipient_curve25519
        )

        # Sign encrypted message
        encrypted_bytes = base64.b64decode(encrypted_b64)
        nonce_bytes = base64.b64decode(nonce_b64)
        signature = SignatureManager.sign_encrypted_message(
            encrypted_bytes, nonce_bytes, sender_signing_key
        )
        signature_b64 = base64.b64encode(signature).decode()

        # Send to server
        message = await self.messaging_client.send_message(
            sender_id=self.key_manager.user_id,
            recipient_id=recipient.user_id,
            encrypted_message=encrypted_b64,
            nonce=nonce_b64,
            signature=signature_b64,
            timestamp=datetime.now()
        )

        logger.info(f"Message sent to {recipient.alias}")
        return message

    async def decrypt_message(self, message: Message, sender: Contact) -> str:
        """Decrypt a received message.

        Args:
            message: The encrypted message.
            sender: The contact who sent the message.

        Returns:
            The decrypted plain text.
        """
        # Get sender's public key
        sender_public_key = KeyManager.base64_to_public_key(sender.public_key)
        sender_curve25519 = EncryptionManager.convert_ed25519_to_curve25519(
            sender_public_key
        )

        # Get recipient's (our) private key
        my_private_key = self.key_manager.signing_key.to_curve25519_private_key()

        # Decrypt message
        plaintext = EncryptionManager.decrypt_from_base64(
            message.encrypted_message,
            message.nonce,
            my_private_key,
            sender_curve25519
        )

        logger.debug(f"Message decrypted from {sender.alias}")
        return plaintext

    def start_message_polling(
        self,
        on_message: Callable[[Message, str], None]
    ) -> None:
        """Start polling for new messages.

        Args:
            on_message: Callback function called with (message, decrypted_plaintext).
        """
        if self._polling:
            logger.warning("Polling already started")
            return

        self._polling = True
        self._on_message_callback = on_message

        # Set up message handler in messaging client
        self.messaging_client.set_message_handler(self._handle_received_message)

        # Start polling
        asyncio.create_task(
            self.messaging_client.start_polling(self.key_manager.user_id)
        )

        logger.info("Message polling started")

    async def stop_message_polling(self) -> None:
        """Stop polling for new messages."""
        if not self._polling:
            return

        self._polling = False
        await self.messaging_client.stop_polling()
        self._on_message_callback = None

        logger.info("Message polling stopped")

    def _handle_received_message(self, message: Message) -> None:
        """Handle a received message from polling.

        Args:
            message: The received message.
        """
        if not self._on_message_callback:
            return

        # Pass message to callback - let the screen handle decryption
        # since it has access to ContactService
        self._on_message_callback(message, "")

    def get_messages(self, contact: Contact, limit: int = 100) -> List[Message]:
        """Get messages with a contact.

        Args:
            contact: The contact.
            limit: Maximum number of messages.

        Returns:
            List of messages.
        """
        return self.database.get_messages_by_contact(contact.user_id, limit)

    async def register_with_server(self) -> tuple[str, datetime]:
        """Register public key with server.

        Returns:
            Tuple of (user_id, registered_at).
        """
        public_key_b64 = self.key_manager.public_key_base64

        # Create self-signature to prove key ownership
        public_key_bytes = base64.b64decode(public_key_b64)
        signature = self.key_manager.signing_key.sign(public_key_bytes)
        signature_b64 = base64.b64encode(signature.signature).decode()

        return await self.messaging_client.register_public_key(public_key_b64, signature_b64)

    async def close(self) -> None:
        """Clean up resources."""
        await self.stop_message_polling()
