"""Message API endpoints."""
from fastapi import APIRouter, HTTPException, status

from server.models.message import (
    MessagePullRequest,
    MessagePullResponse,
    MessageSendRequest,
    MessageSendResponse,
)
from server.models.response import ErrorResponse
from server.services.key_service import key_service
from server.services.message_service import message_service
from server.utils.logger import get_logger
from server.utils.validators import (
    validate_base64,
    validate_message_size,
    validate_timestamp,
    validate_user_id,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post(
    "/send",
    response_model=MessageSendResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "User not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def send_message(request: MessageSendRequest) -> MessageSendResponse:
    """Queue an encrypted message for delivery."""
    try:
        validate_user_id(request.sender_id)
        validate_user_id(request.recipient_id)
        validate_timestamp(request.timestamp)
        validate_base64(request.encrypted_message, "encrypted_message")
        validate_base64(request.nonce, "nonce")
        validate_base64(request.signature, "signature")
        validate_message_size(request.encrypted_message)

        if not key_service.is_user_registered(request.sender_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sender not found",
            )
        if not key_service.is_user_registered(request.recipient_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient not found",
            )

        message_data = await message_service.enqueue_message(
            sender_id=request.sender_id,
            recipient_id=request.recipient_id,
            encrypted_message=request.encrypted_message,
            nonce=request.nonce,
            signature=request.signature,
            timestamp=request.timestamp,
        )
        return MessageSendResponse(**message_data)

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Message send failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error during message send: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post(
    "/pull",
    response_model=MessagePullResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "User not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def pull_messages(request: MessagePullRequest) -> MessagePullResponse:
    """Pull queued messages for a user and mark them online."""
    try:
        validate_user_id(request.user_id)

        if not key_service.is_user_registered(request.user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        key_service.mark_user_online(request.user_id)
        response_data = await message_service.pull_messages(
            user_id=request.user_id,
            acked_seq=request.acked_seq,
            limit=request.limit,
        )
        return MessagePullResponse(**response_data)

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Message pull failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error during message pull: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
