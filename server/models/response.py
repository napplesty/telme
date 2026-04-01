"""Server response models."""
from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="healthy", description="Server health status")
    timestamp: datetime = Field(default_factory=datetime.now, description="Current timestamp")
    version: str = Field(default="0.1.0", description="Server version")


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    timestamp: datetime = Field(default_factory=datetime.now, description="Error timestamp")
