"""Key management service."""
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Optional

from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError, CryptoError

from server.config import config
from server.utils.logger import get_logger

logger = get_logger(__name__)


class KeyService:
    """Service for managing user public keys."""

    def __init__(self):
        """Initialize key service with in-memory storage."""
        self.reset()

    def reset(self) -> None:
        """Reset all in-memory key and presence state."""
        # This service intentionally keeps all state in memory.
        # Format: {user_id: {"public_key": str, "registered_at": datetime}}
        self._keys_store: dict[str, dict] = {}
        # Online users with last seen timestamp
        # Format: {user_id: last_seen_timestamp}
        self._online_users: dict[str, datetime] = {}

    def register_key(self, public_key_b64: str, signature_b64: str) -> tuple[str, datetime]:
        """Register a new public key.

        Args:
            public_key_b64: Base64-encoded public key.
            signature_b64: Signature proving ownership of the key.

        Returns:
            Tuple of (user_id, registered_at).

        Raises:
            ValueError: If registration fails.
        """
        try:
            # Decode public key
            public_key_bytes = base64.b64decode(public_key_b64)
            if len(public_key_bytes) != 32:
                raise ValueError("Invalid public key length")

            # Create verify key
            verify_key = VerifyKey(public_key_bytes)

            # Decode and verify signature
            signature_bytes = base64.b64decode(signature_b64)

            # Verify signature (signing the public key itself)
            try:
                verify_key.verify(public_key_bytes, signature_bytes)
            except BadSignatureError:
                raise ValueError("Invalid signature - cannot verify key ownership")

            # Generate user ID (hash of public key)
            user_id = hashlib.sha256(public_key_bytes).hexdigest()

            # Store key
            registered_at = datetime.now()
            self._keys_store[user_id] = {
                "public_key": public_key_b64,
                "registered_at": registered_at
            }

            logger.info(f"Registered public key for user {user_id[:8]}...")

            return user_id, registered_at

        except Exception as e:
            logger.error(f"Failed to register key: {e}")
            raise ValueError(f"Key registration failed: {e}") from e

    def get_key(self, user_id: str) -> Optional[str]:
        """Get public key for a user.

        Args:
            user_id: User's public key hash.

        Returns:
            Base64-encoded public key or None if not found.
        """
        user_data = self._keys_store.get(user_id)
        return user_data["public_key"] if user_data else None

    def is_user_registered(self, user_id: str) -> bool:
        """Check if a user is registered.

        Args:
            user_id: User's public key hash.

        Returns:
            True if user is registered, False otherwise.
        """
        return user_id in self._keys_store

    def mark_user_online(self, user_id: str) -> None:
        """Mark a user as online.

        Args:
            user_id: User's public key hash.
        """
        self._online_users[user_id] = datetime.now()

    def is_user_online(self, user_id: str) -> bool:
        """Check if a user is online.

        A user is considered online if they've been active in the last 30 seconds.

        Args:
            user_id: User's public key hash.

        Returns:
            True if user is online, False otherwise.
        """
        last_seen = self._online_users.get(user_id)
        if last_seen is None:
            return False

        # User is online if last seen within 30 seconds
        online_threshold = datetime.now() - timedelta(seconds=30)
        return last_seen > online_threshold

    def get_online_users(self) -> list[str]:
        """Get list of online user IDs.

        Returns:
            List of online user IDs.
        """
        online_threshold = datetime.now() - timedelta(seconds=30)
        return [
            user_id for user_id, last_seen in self._online_users.items()
            if last_seen > online_threshold
        ]

    def cleanup_stale_data(self) -> None:
        """Clean up stale data (users not seen for a while)."""
        # Remove offline users from tracking after 1 hour
        stale_threshold = datetime.now() - timedelta(hours=1)
        stale_users = [
            user_id for user_id, last_seen in self._online_users.items()
            if last_seen < stale_threshold
        ]

        for user_id in stale_users:
            del self._online_users[user_id]

        if stale_users:
            logger.info(f"Cleaned up {len(stale_users)} stale users")


# Global key service instance
key_service = KeyService()
