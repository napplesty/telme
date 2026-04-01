"""Digital signature module using ed25519."""
import base64
from typing import Union

from nacl.signing import SigningKey, VerifyKey, SignedMessage
from nacl.exceptions import BadSignatureError

from client.utils.logger import get_logger

logger = get_logger(__name__)


class SignatureManager:
    """Handles message signing and signature verification using ed25519."""

    @staticmethod
    def sign_message(message: Union[str, bytes], signing_key: SigningKey) -> bytes:
        """Sign a message using ed25519 private key.

        Args:
            message: Message to sign (string or bytes).
            signing_key: SigningKey (private key) to sign with.

        Returns:
            Digital signature as bytes.
        """
        # Convert string to bytes if necessary
        if isinstance(message, str):
            message_bytes = message.encode("utf-8")
        else:
            message_bytes = message

        # Sign the message
        signed: SignedMessage = signing_key.sign(message_bytes)

        # Extract just the signature (last 64 bytes)
        # signed.message contains the original message
        # signed.signature contains just the signature
        signature = signed.signature

        logger.debug(f"Message signed, signature: {base64.b64encode(signature).decode()[:20]}...")

        return signature

    @staticmethod
    def verify_signature(
        message: Union[str, bytes],
        signature: bytes,
        verify_key: VerifyKey
    ) -> bool:
        """Verify a message signature using ed25519 public key.

        Args:
            message: Original message (string or bytes).
            signature: Digital signature bytes.
            verify_key: VerifyKey (public key) to verify with.

        Returns:
            True if signature is valid, False otherwise.
        """
        # Convert string to bytes if necessary
        if isinstance(message, str):
            message_bytes = message.encode("utf-8")
        else:
            message_bytes = message

        # Verify the signature — BadSignatureError means tampered, not a bug
        try:
            verify_key.verify(message_bytes, signature)
        except BadSignatureError:
            logger.warning("Invalid signature - message may be tampered")
            return False

        logger.debug("Signature verified successfully")
        return True

    @staticmethod
    def sign_to_base64(message: Union[str, bytes], signing_key: SigningKey) -> str:
        """Sign a message and return base64-encoded signature.

        Args:
            message: Message to sign.
            signing_key: SigningKey to sign with.

        Returns:
            Base64-encoded signature string.
        """
        signature = SignatureManager.sign_message(message, signing_key)
        return base64.b64encode(signature).decode("utf-8")

    @staticmethod
    def verify_from_base64(
        message: Union[str, bytes],
        signature_b64: str,
        verify_key: VerifyKey
    ) -> bool:
        """Verify a base64-encoded signature.

        Args:
            message: Original message.
            signature_b64: Base64-encoded signature.
            verify_key: VerifyKey to verify with.

        Returns:
            True if signature is valid, False otherwise.
        """
        signature = base64.b64decode(signature_b64)
        return SignatureManager.verify_signature(message, signature, verify_key)

    @staticmethod
    def sign_encrypted_message(
        encrypted_message: bytes,
        nonce: bytes,
        signing_key: SigningKey
    ) -> bytes:
        """Sign an encrypted message with its nonce.

        This signs the combination of encrypted_message + nonce to ensure
        both parts are authentic and belong together.

        Args:
            encrypted_message: Encrypted message bytes.
            nonce: Nonce used for encryption.
            signing_key: SigningKey to sign with.

        Returns:
            Digital signature bytes.
        """
        # Combine encrypted message and nonce, then sign
        data_to_sign = encrypted_message + nonce
        return SignatureManager.sign_message(data_to_sign, signing_key)

    @staticmethod
    def verify_encrypted_message(
        encrypted_message: bytes,
        nonce: bytes,
        signature: bytes,
        verify_key: VerifyKey
    ) -> bool:
        """Verify an encrypted message signature.

        Args:
            encrypted_message: Encrypted message bytes.
            nonce: Nonce used for encryption.
            signature: Digital signature bytes.
            verify_key: VerifyKey to verify with.

        Returns:
            True if signature is valid, False otherwise.
        """
        # Combine encrypted message and nonce, then verify
        data_to_verify = encrypted_message + nonce
        return SignatureManager.verify_signature(data_to_verify, signature, verify_key)
