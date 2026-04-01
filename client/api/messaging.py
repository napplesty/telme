"""Messaging API wrapper for client workflows."""
import asyncio
from datetime import datetime
from typing import Callable, Optional

from client.api.client import APIClient
from client.config import config
from client.storage.database import Database
from client.storage.models import Message, MessageDirection, MessageStatus
from client.utils.logger import get_logger

logger = get_logger(__name__)


class MessagingClient:
    """High-level client for key registration, send, pull, and polling."""

    def __init__(self, api_client: APIClient, database: Database):
        self.api_client = api_client
        self.database = database
        self._message_handler: Optional[Callable[[Message], None]] = None
        self._polling_task: Optional[asyncio.Task] = None
        self._polling_user_id: Optional[str] = None

    async def register_public_key(self, public_key: str, signature: str) -> tuple[str, datetime]:
        """Register public key with the server."""
        response = await self.api_client.post(
            "/keys/register",
            json={
                "public_key": public_key,
                "signature": signature,
                "timestamp": datetime.now().isoformat(),
            },
        )
        return response["user_id"], datetime.fromisoformat(response["registered_at"])

    async def send_message(
        self,
        sender_id: str,
        recipient_id: str,
        encrypted_message: str,
        nonce: str,
        signature: str,
        timestamp: datetime,
    ) -> Message:
        """Send an encrypted message via the server and store it locally."""
        response = await self.api_client.post(
            "/messages/send",
            json={
                "sender_id": sender_id,
                "recipient_id": recipient_id,
                "encrypted_message": encrypted_message,
                "nonce": nonce,
                "signature": signature,
                "timestamp": timestamp.isoformat(),
            },
        )

        return self.database.add_message(
            message_id=response["message_id"],
            sender_id=response["sender_id"],
            recipient_id=response["recipient_id"],
            encrypted_message=response["encrypted_message"],
            nonce=response["nonce"],
            signature=response["signature"],
            direction=MessageDirection.SENT,
            status=MessageStatus(response["status"]),
            timestamp=datetime.fromisoformat(response["timestamp"]),
            server_seq=response["server_seq"],
        )

    async def pull_messages(
        self,
        user_id: str,
    ) -> tuple[list[Message], int, bool]:
        """Pull messages from server and persist them locally."""
        sync_state = self.database.get_sync_state(user_id)

        response = await self.api_client.post(
            "/messages/pull",
            json={
                "user_id": user_id,
                "acked_seq": sync_state.acked_seq,
                "limit": config.PULL_BATCH_SIZE,
            },
        )

        messages, _ = self.database.persist_received_batch(
            user_id=user_id,
            messages_data=response["messages"],
            acked_seq=response["last_seq"],
        )
        return messages, response["last_seq"], response["has_more"]

    def set_message_handler(self, callback: Callable[[Message], None]) -> None:
        """Set callback for newly received messages while polling."""
        self._message_handler = callback

    async def start_polling(self, user_id: str) -> None:
        """Start a single polling loop for new messages."""
        if self._polling_task and not self._polling_task.done():
            logger.warning("Polling already running")
            return

        self._polling_user_id = user_id
        self._polling_task = asyncio.current_task()

        try:
            while True:
                messages, _, _ = await self.pull_messages(user_id)
                if self._message_handler:
                    for message in messages:
                        self._message_handler(message)
                await asyncio.sleep(config.POLL_INTERVAL)
        except asyncio.CancelledError:
            logger.info("Message polling cancelled")
            raise
        finally:
            self._polling_task = None
            self._polling_user_id = None

    async def stop_polling(self) -> None:
        """Stop the active polling loop if one exists."""
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            logger.info("Message polling stopped")
