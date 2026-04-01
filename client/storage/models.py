"""Data models for client storage."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class MessageDirection(str, Enum):
    """Message direction enum."""

    SENT = "sent"
    RECEIVED = "received"


class MessageStatus(str, Enum):
    """Message status enum."""

    PENDING = "pending"
    QUEUED = "queued"
    FAILED = "failed"


@dataclass
class Contact:
    """Contact data model."""

    id: Optional[int]
    user_id: str
    public_key: str
    alias: str
    created_at: datetime

    @classmethod
    def from_dict(cls, data: dict) -> "Contact":
        """Create Contact from dictionary."""
        return cls(
            id=data.get("id"),
            user_id=data["user_id"],
            public_key=data["public_key"],
            alias=data["alias"],
            created_at=datetime.fromisoformat(data["created_at"])
            if isinstance(data["created_at"], str)
            else data["created_at"],
        )

    def to_dict(self) -> dict:
        """Convert Contact to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "public_key": self.public_key,
            "alias": self.alias,
            "created_at": self.created_at.isoformat()
            if isinstance(self.created_at, datetime)
            else self.created_at,
        }


@dataclass
class Message:
    """Message data model."""

    id: Optional[int]
    message_id: str
    sender_id: str
    recipient_id: str
    encrypted_message: str
    nonce: str
    signature: str
    direction: MessageDirection
    status: MessageStatus
    timestamp: datetime
    server_seq: Optional[int] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """Create Message from dictionary."""
        return cls(
            id=data.get("id"),
            message_id=data["message_id"],
            sender_id=data["sender_id"],
            recipient_id=data["recipient_id"],
            encrypted_message=data["encrypted_message"],
            nonce=data["nonce"],
            signature=data["signature"],
            direction=MessageDirection(data["direction"]),
            status=MessageStatus(data["status"]),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if isinstance(data["timestamp"], str)
            else data["timestamp"],
            server_seq=data.get("server_seq"),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at") and isinstance(data["created_at"], str)
            else data.get("created_at"),
        )

    def to_dict(self) -> dict:
        """Convert Message to dictionary."""
        return {
            "id": self.id,
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "encrypted_message": self.encrypted_message,
            "nonce": self.nonce,
            "signature": self.signature,
            "direction": self.direction.value,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat()
            if isinstance(self.timestamp, datetime)
            else self.timestamp,
            "server_seq": self.server_seq,
            "created_at": self.created_at.isoformat()
            if self.created_at and isinstance(self.created_at, datetime)
            else self.created_at,
        }


@dataclass
class SyncState:
    """Per-user synchronization state for polling recovery."""

    user_id: str
    acked_seq: int
    updated_at: datetime

    @classmethod
    def from_dict(cls, data: dict) -> "SyncState":
        """Create SyncState from dictionary."""
        return cls(
            user_id=data["user_id"],
            acked_seq=data["acked_seq"],
            updated_at=datetime.fromisoformat(data["updated_at"])
            if isinstance(data["updated_at"], str)
            else data["updated_at"],
        )


@dataclass
class Conversation:
    """Conversation data model for UI display."""

    contact_id: int
    contact_alias: str
    last_message: Optional[str]
    last_message_time: Optional[datetime]
    unread_count: int

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        """Create Conversation from dictionary."""
        return cls(
            contact_id=data["contact_id"],
            contact_alias=data["contact_alias"],
            last_message=data.get("last_message"),
            last_message_time=datetime.fromisoformat(data["last_message_time"])
            if data.get("last_message_time") and isinstance(data["last_message_time"], str)
            else data.get("last_message_time"),
            unread_count=data.get("unread_count", 0),
        )
