"""Server key data models."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class KeyRegisterRequest(BaseModel):
    """Request for registering a public key."""
    public_key: str = Field(..., description="Base64-encoded ed25519 public key")
    signature: str = Field(..., description="Signature of public key to prove ownership")
    timestamp: datetime = Field(default_factory=datetime.now, description="Registration timestamp")


class KeyRegisterResponse(BaseModel):
    """Response for key registration."""
    user_id: str = Field(..., description="User ID (public key hash)")
    registered_at: datetime = Field(..., description="Registration timestamp")


class KeyResponse(BaseModel):
    """Response for key query."""
    user_id: str = Field(..., description="User ID (public key hash)")
    public_key: str = Field(..., description="Base64-encoded public key")
