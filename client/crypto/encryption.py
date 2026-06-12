"""Encryption and decryption module using XSalsa20-Poly1305 with zlib compression."""
import base64
import zlib
from typing import Tuple

from nacl.public import PrivateKey, PublicKey, Box
from nacl.signing import VerifyKey

from client.utils.logger import get_logger

logger = get_logger(__name__)

# Compression level 6: good balance between speed and ratio for text
_COMPRESS_LEVEL = 6


class EncryptionManager:
    """Handles message encryption and decryption using XSalsa20-Poly1305.

    All messages are compressed with zlib before encryption and decompressed
    after decryption. This significantly reduces ciphertext size for plaintext
    messages (typically 40-60% smaller for Chinese/English text).
    """

    @staticmethod
    def convert_ed25519_to_curve25519(ed25519_key: VerifyKey) -> PublicKey:
        """Convert ed25519 public key to curve25519 for encryption.

        Args:
            ed25519_key: Ed25519 public key (VerifyKey).

        Returns:
            Curve25519 public key for encryption.
        """
        curve25519_public = ed25519_key.to_curve25519_public_key()
        return curve25519_public

    @staticmethod
    def encrypt_message(
        plaintext: str,
        sender_private_key: PrivateKey,
        recipient_public_key: PublicKey
    ) -> Tuple[bytes, bytes]:
        """Compress and encrypt a message using zlib + XSalsa20-Poly1305.

        Args:
            plaintext: Plain text message to encrypt.
            sender_private_key: Sender's private key for ECDH.
            recipient_public_key: Recipient's public key for ECDH.

        Returns:
            Tuple of (encrypted_message, nonce).
        """
        box = Box(sender_private_key, recipient_public_key)

        # Compress before encryption (encrypted data is incompressible)
        plaintext_bytes = plaintext.encode("utf-8")
        compressed = zlib.compress(plaintext_bytes, _COMPRESS_LEVEL)

        encrypted = box.encrypt(compressed)

        nonce = encrypted[:24]
        ciphertext = encrypted[24:]

        logger.debug(
            f"Message encrypted: {len(plaintext_bytes)}B → "
            f"{len(compressed)}B compressed → {len(ciphertext)}B ciphertext"
        )

        return ciphertext, nonce

    @staticmethod
    def decrypt_message(
        ciphertext: bytes,
        nonce: bytes,
        recipient_private_key: PrivateKey,
        sender_public_key: PublicKey
    ) -> str:
        """Decrypt and decompress a message using XSalsa20-Poly1305 + zlib.

        Args:
            ciphertext: Encrypted message bytes.
            nonce: Nonce used for encryption.
            recipient_private_key: Recipient's private key for ECDH.
            sender_public_key: Sender's public key for ECDH.

        Returns:
            Decrypted plain text message.
        """
        box = Box(recipient_private_key, sender_public_key)

        encrypted = nonce + ciphertext
        compressed = box.decrypt(encrypted)

        # Decompress after decryption
        plaintext_bytes = zlib.decompress(compressed)
        plaintext = plaintext_bytes.decode("utf-8")

        logger.debug("Message decrypted and decompressed successfully")

        return plaintext

    @staticmethod
    def encrypt_to_base64(
        plaintext: str,
        sender_private_key: PrivateKey,
        recipient_public_key: PublicKey
    ) -> Tuple[str, str]:
        """Encrypt a message and return base64-encoded strings.

        Args:
            plaintext: Plain text message to encrypt.
            sender_private_key: Sender's private key.
            recipient_public_key: Recipient's public key.

        Returns:
            Tuple of (encrypted_message_base64, nonce_base64).
        """
        ciphertext, nonce = EncryptionManager.encrypt_message(
            plaintext, sender_private_key, recipient_public_key
        )

        ciphertext_b64 = base64.b64encode(ciphertext).decode("utf-8")
        nonce_b64 = base64.b64encode(nonce).decode("utf-8")

        return ciphertext_b64, nonce_b64

    @staticmethod
    def decrypt_from_base64(
        ciphertext_b64: str,
        nonce_b64: str,
        recipient_private_key: PrivateKey,
        sender_public_key: PublicKey
    ) -> str:
        """Decrypt a base64-encoded message.

        Args:
            ciphertext_b64: Base64-encoded ciphertext.
            nonce_b64: Base64-encoded nonce.
            recipient_private_key: Recipient's private key.
            sender_public_key: Sender's public key.

        Returns:
            Decrypted plain text message.
        """
        ciphertext = base64.b64decode(ciphertext_b64)
        nonce = base64.b64decode(nonce_b64)

        return EncryptionManager.decrypt_message(
            ciphertext, nonce, recipient_private_key, sender_public_key
        )
