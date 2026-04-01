"""Health check API endpoint."""
from fastapi import APIRouter

from server.models.response import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns:
        Health check response with server status.
    """
    return HealthResponse()
