"""In-memory message queue service with per-recipient locking and optimized lookups."""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from server.config import config
from server.services.key_service import key_service
from server.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class StoredMessage:
    """Internal representation of a queued message.

    Messages within a recipient's queue are always ordered by server_seq (ascending)
    and stored_at (ascending, since seq is assigned monotonically).
    """

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


class _RecipientQueue:
    """Per-recipient message queue with its own lock for fine-grained concurrency."""

    __slots__ = ("_messages", "_next_seq", "_lock")

    def __init__(self) -> None:
        self._messages: list[StoredMessage] = []
        self._next_seq: int = 1
        self._lock = asyncio.Lock()

    async def enqueue(
        self,
        sender_id: str,
        recipient_id: str,
        encrypted_message: str,
        nonce: str,
        signature: str,
        timestamp: datetime,
    ) -> StoredMessage:
        """Append a message to this recipient's queue."""
        async with self._lock:
            seq = self._next_seq
            msg = StoredMessage(
                message_id=str(uuid4()),
                server_seq=seq,
                sender_id=sender_id,
                recipient_id=recipient_id,
                encrypted_message=encrypted_message,
                nonce=nonce,
                signature=signature,
                timestamp=timestamp,
                stored_at=datetime.now(),
            )
            self._messages.append(msg)
            self._next_seq = seq + 1
        return msg

    async def pull(self, acked_seq: int, limit: int) -> dict:
        """Return messages with server_seq > acked_seq, up to limit.

        Uses binary search since messages are ordered by server_seq.
        """
        async with self._lock:
            messages = self._messages
            if not messages:
                return {"messages": [], "last_seq": acked_seq, "has_more": False}

            # Binary search: find first message with server_seq > acked_seq
            # All messages are sorted by server_seq (ascending, no gaps within queue)
            lo = 0
            hi = len(messages)
            while lo < hi:
                mid = (lo + hi) // 2
                if messages[mid].server_seq <= acked_seq:
                    lo = mid + 1
                else:
                    hi = mid

            pending_count = len(messages) - lo
            end = lo + min(limit, pending_count)
            batch = messages[lo:end]
            has_more = end < len(messages)
            last_seq = batch[-1].server_seq if batch else acked_seq

        return {
            "messages": [m.to_pull_dict() for m in batch],
            "last_seq": last_seq,
            "has_more": has_more,
        }

    async def cleanup_expired(self, expiry_threshold: datetime) -> int:
        """Remove messages stored before expiry_threshold.

        Since messages are appended in chronological order (stored_at is monotonically
        increasing), we can find the cutoff point with a linear scan from the front
        and slice off the expired prefix in O(k) where k = expired count.
        """
        async with self._lock:
            messages = self._messages
            if not messages:
                return 0

            # Fast path: nothing expired
            if messages[0].stored_at >= expiry_threshold:
                return 0

            # Fast path: everything expired
            if messages[-1].stored_at < expiry_threshold:
                removed = len(messages)
                self._messages = []
                return removed

            # Find cutoff: first message that is NOT expired
            cutoff = 0
            for i, msg in enumerate(messages):
                if msg.stored_at >= expiry_threshold:
                    cutoff = i
                    break
            else:
                cutoff = len(messages)

            if cutoff > 0:
                self._messages = messages[cutoff:]
                return cutoff

            return 0

    @property
    def is_empty(self) -> bool:
        return len(self._messages) == 0

    @property
    def message_count(self) -> int:
        return len(self._messages)


class MessageService:
    """In-memory message service with per-recipient locking and TTL cleanup.

    Performance characteristics:
    - enqueue: O(1) amortized (append to recipient queue, per-recipient lock)
    - pull: O(log n + k) where n = queue size, k = batch size (binary search + slice)
    - cleanup: O(R * k_i) where R = recipients, k_i = expired msgs per recipient
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Reset all in-memory queued message state."""
        self._queues: dict[str, _RecipientQueue] = {}
        # Lightweight lock only for queue creation (not for per-message operations)
        self._queues_lock = asyncio.Lock()

    async def _get_or_create_queue(self, recipient_id: str) -> _RecipientQueue:
        """Get or lazily create a recipient queue."""
        queue = self._queues.get(recipient_id)
        if queue is not None:
            return queue

        async with self._queues_lock:
            # Double-check after acquiring lock
            queue = self._queues.get(recipient_id)
            if queue is None:
                queue = _RecipientQueue()
                self._queues[recipient_id] = queue
            return queue

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

        queue = await self._get_or_create_queue(recipient_id)
        stored_message = await queue.enqueue(
            sender_id=sender_id,
            recipient_id=recipient_id,
            encrypted_message=encrypted_message,
            nonce=nonce,
            signature=signature,
            timestamp=timestamp,
        )

        logger.debug(
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
        queue = self._queues.get(user_id)
        if queue is None:
            return {"messages": [], "last_seq": acked_seq, "has_more": False}

        return await queue.pull(acked_seq, limit)

    async def cleanup_expired_messages(self) -> int:
        """Remove expired queued messages based on server-side TTL.

        Iterates over all recipient queues and removes expired prefixes.
        Empty queues are pruned from the registry.
        """
        expiry_threshold = datetime.now() - timedelta(seconds=config.MESSAGE_TTL)
        removed_count = 0
        empty_queues: list[str] = []

        # Snapshot keys to avoid mutation during iteration
        recipient_ids = list(self._queues.keys())

        for recipient_id in recipient_ids:
            queue = self._queues.get(recipient_id)
            if queue is None:
                continue

            removed = await queue.cleanup_expired(expiry_threshold)
            removed_count += removed

            if queue.is_empty:
                empty_queues.append(recipient_id)

        # Prune empty queues under the queues lock
        if empty_queues:
            async with self._queues_lock:
                for recipient_id in empty_queues:
                    queue = self._queues.get(recipient_id)
                    if queue is not None and queue.is_empty:
                        del self._queues[recipient_id]

        if removed_count:
            logger.info(f"Cleaned up {removed_count} expired queued messages")

        return removed_count


message_service = MessageService()
