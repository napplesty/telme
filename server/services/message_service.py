"""In-memory message queue service."""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from server.config import config
from server.services.key_service import key_service
from server.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class StoredMessage:
    """Internal representation of a queued message."""

    message_id: str
    server_seq: int
    sender_id: str
    recipient_id: str
    encrypted_message: str
    nonce: str
    signature: str
    timestamp: datetime
    stored_at: datetime

    def to_pull_dict(self) -> dict:
        """Convert message to pull API payload."""
        return {
            "message_id": self.message_id,
            "server_seq": self.server_seq,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "encrypted_message": self.encrypted_message,
            "nonce": self.nonce,
            "signature": self.signature,
            "timestamp": self.timestamp,
        }

    def to_send_dict(self) -> dict:
        """Convert message to send API payload."""
        data = self.to_pull_dict()
        data["status"] = "queued"
        return data


class MessageService:
    """In-memory message service with TTL cleanup."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Reset all in-memory queued message state."""
        self._messages_by_recipient: dict[str, list[StoredMessage]] = {}
        self._next_seq_by_recipient: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def enqueue_message(
        self,
        sender_id: str,
        recipient_id: str,
        encrypted_message: str,
        nonce: str,
        signature: str,
        timestamp: datetime,
    ) -> dict:
        """Store a new message for later pull."""
        if not key_service.is_user_registered(sender_id):
            raise ValueError("Sender is not registered")
        if not key_service.is_user_registered(recipient_id):
            raise ValueError("Recipient is not registered")

        async with self._lock:
            next_seq = self._next_seq_by_recipient.get(recipient_id, 1)
            stored_message = StoredMessage(
                message_id=str(uuid4()),
                server_seq=next_seq,
                sender_id=sender_id,
                recipient_id=recipient_id,
                encrypted_message=encrypted_message,
                nonce=nonce,
                signature=signature,
                timestamp=timestamp,
                stored_at=datetime.now(),
            )
            self._messages_by_recipient.setdefault(recipient_id, []).append(stored_message)
            self._next_seq_by_recipient[recipient_id] = next_seq + 1

        logger.info(
            f"Queued message {stored_message.message_id} for {recipient_id[:8]}... "
            f"server_seq={stored_message.server_seq}"
        )
        return stored_message.to_send_dict()

    async def pull_messages(
        self,
        user_id: str,
        acked_seq: int,
        limit: int,
    ) -> dict:
        """Return queued messages for a user."""
        async with self._lock:
            queued_messages = self._messages_by_recipient.get(user_id, [])
            pending_messages = [
                message for message in queued_messages if message.server_seq > acked_seq
            ]
            batch = pending_messages[:limit]
            has_more = len(pending_messages) > len(batch)
            last_seq = batch[-1].server_seq if batch else acked_seq

        return {
            "messages": [message.to_pull_dict() for message in batch],
            "last_seq": last_seq,
            "has_more": has_more,
        }

    async def cleanup_expired_messages(self) -> int:
        """Remove expired queued messages based on server-side TTL."""
        expiry_threshold = datetime.now() - timedelta(seconds=config.MESSAGE_TTL)
        removed_count = 0

        async with self._lock:
            empty_recipients: list[str] = []
            for recipient_id, queued_messages in self._messages_by_recipient.items():
                retained_messages = [
                    message for message in queued_messages if message.stored_at >= expiry_threshold
                ]
                removed_count += len(queued_messages) - len(retained_messages)

                if retained_messages:
                    self._messages_by_recipient[recipient_id] = retained_messages
                else:
                    empty_recipients.append(recipient_id)

            for recipient_id in empty_recipients:
                del self._messages_by_recipient[recipient_id]

        if removed_count:
            logger.info(f"Cleaned up {removed_count} expired queued messages")

        return removed_count


message_service = MessageService()
