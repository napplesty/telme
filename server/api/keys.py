"""Key management API endpoints."""
from fastapi import APIRouter, HTTPException, status

from server.models.key import KeyRegisterRequest, KeyRegisterResponse, KeyResponse
from server.models.response import ErrorResponse
from server.services.key_service import key_service
from server.utils.logger import get_logger
from server.utils.validators import validate_base64, validate_timestamp

logger = get_logger(__name__)

router = APIRouter(prefix="/keys", tags=["keys"])


@router.post(
    "/register",
    response_model=KeyRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
async def register_key(request: KeyRegisterRequest) -> KeyRegisterResponse:
    """Register a new public key.

    Args:
        request: Key registration request with public key and signature.

    Returns:
        KeyRegisterResponse with user ID and registration timestamp.

    Raises:
        HTTPException: If registration fails.
    """
    try:
        # Validate timestamp
        validate_timestamp(request.timestamp)

        # Validate base64 encoding
        validate_base64(request.public_key, "public_key")
        validate_base64(request.signature, "signature")

        # Register key
        user_id, registered_at = key_service.register_key(
            public_key_b64=request.public_key,
            signature_b64=request.signature
        )

        logger.info(f"Key registered successfully: {user_id[:8]}...")

        return KeyRegisterResponse(
            user_id=user_id,
            registered_at=registered_at
        )

    except ValueError as e:
        logger.error(f"Key registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error during key registration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/{user_id}",
    response_model=KeyResponse,
    responses={
        404: {"model": ErrorResponse, "description": "User not found"},
    }
)
async def get_key(user_id: str) -> KeyResponse:
    """Get public key for a user.

    Args:
        user_id: User's public key hash.

    Returns:
        KeyResponse with user ID and public key.

    Raises:
        HTTPException: If user not found.
    """
    public_key = key_service.get_key(user_id)

    if public_key is None:
        logger.warning(f"Key not found for user: {user_id[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return KeyResponse(
        user_id=user_id,
        public_key=public_key
    )
