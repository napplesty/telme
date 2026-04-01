"""Server message data models."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MessageSendRequest(BaseModel):
    """Request for sending an encrypted message."""

    sender_id: str = Field(..., description="Sender user ID")
    recipient_id: str = Field(..., description="Recipient user ID")
    encrypted_message: str = Field(..., description="Base64-encoded encrypted message")
    nonce: str = Field(..., description="Base64-encoded nonce")
    signature: str = Field(..., description="Base64-encoded signature")
    timestamp: datetime = Field(default_factory=datetime.now, description="Client timestamp")


class MessageSendResponse(BaseModel):
    """Response for message send."""

    message_id: str = Field(..., description="Server-assigned message ID")
    sender_id: str = Field(..., description="Sender user ID")
    recipient_id: str = Field(..., description="Recipient user ID")
    encrypted_message: str = Field(..., description="Base64-encoded encrypted message")
    nonce: str = Field(..., description="Base64-encoded nonce")
    signature: str = Field(..., description="Base64-encoded signature")
    timestamp: datetime = Field(..., description="Client timestamp")
    server_seq: int = Field(..., description="Per-recipient sequence number")
    status: Literal["queued"] = Field(default="queued", description="Queue status")


class PulledMessage(BaseModel):
    """Message item returned by pull API."""

    message_id: str = Field(..., description="Server-assigned message ID")
    server_seq: int = Field(..., description="Per-recipient sequence number")
    sender_id: str = Field(..., description="Sender user ID")
    recipient_id: str = Field(..., description="Recipient user ID")
    encrypted_message: str = Field(..., description="Base64-encoded encrypted message")
    nonce: str = Field(..., description="Base64-encoded nonce")
    signature: str = Field(..., description="Base64-encoded signature")
    timestamp: datetime = Field(..., description="Client timestamp")


class MessagePullRequest(BaseModel):
    """Request for pulling queued messages."""

    user_id: str = Field(..., description="Recipient user ID")
    acked_seq: int = Field(..., ge=0, description="Last acknowledged sequence number")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum messages to return")


class MessagePullResponse(BaseModel):
    """Response for queued message pull."""

    messages: list[PulledMessage] = Field(default_factory=list, description="Queued messages")
    last_seq: int = Field(..., description="Last sequence number in this batch")
    has_more: bool = Field(default=False, description="Whether more queued messages remain")
