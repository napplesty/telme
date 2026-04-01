"""Server validation utilities."""
import base64
from datetime import datetime, timedelta

from server.config import config
from server.utils.logger import get_logger

logger = get_logger(__name__)


def validate_base64(value: str, name: str) -> bytes:
    """Validate and decode a base64-encoded value.

    Args:
        value: Base64-encoded string.
        name: Name of the field (for error messages).

    Returns:
        Decoded bytes.

    Raises:
        ValueError: If value is not valid base64.
    """
    try:
        return base64.b64decode(value)
    except Exception as e:
        logger.error(f"Invalid base64 for {name}: {e}")
        raise ValueError(f"Invalid base64 encoding for {name}") from e


def validate_timestamp(timestamp: datetime, tolerance_seconds: int = None) -> None:
    """Validate that timestamp is within acceptable range.

    Prevents replay attacks by rejecting messages with old or future timestamps.

    Args:
        timestamp: Timestamp to validate.
        tolerance_seconds: Tolerance in seconds (defaults to config value).

    Raises:
        ValueError: If timestamp is outside acceptable range.
    """
    if tolerance_seconds is None:
        tolerance_seconds = config.TIMESTAMP_TOLERANCE

    now = datetime.now()
    min_time = now - timedelta(seconds=tolerance_seconds)
    max_time = now + timedelta(seconds=tolerance_seconds)

    if timestamp < min_time:
        logger.warning(f"Timestamp too old: {timestamp}")
        raise ValueError("Timestamp is too old - possible replay attack")

    if timestamp > max_time:
        logger.warning(f"Timestamp in future: {timestamp}")
        raise ValueError("Timestamp is in the future")


def validate_user_id(user_id: str) -> None:
    """Validate user ID format.

    Args:
        user_id: User ID to validate.

    Raises:
        ValueError: If user ID format is invalid.
    """
    if not user_id:
        raise ValueError("User ID cannot be empty")

    # User ID should be SHA256 hash (64 hex characters)
    if len(user_id) != 64:
        raise ValueError("User ID must be 64 characters (SHA256 hash)")

    if not all(c in "0123456789abcdef" for c in user_id.lower()):
        raise ValueError("User ID must be hexadecimal")


def validate_message_size(encrypted_message: str) -> None:
    """Validate encrypted message size.

    Args:
        encrypted_message: Base64-encoded encrypted message.

    Raises:
        ValueError: If message is too large.
    """
    try:
        message_bytes = base64.b64decode(encrypted_message)
        if len(message_bytes) > config.MAX_MESSAGE_SIZE:
            raise ValueError(
                f"Message too large: {len(message_bytes)} bytes "
                f"(max: {config.MAX_MESSAGE_SIZE} bytes)"
            )
    except Exception as e:
        logger.error(f"Failed to validate message size: {e}")
        raise ValueError("Invalid message format") from e
