"""Encryption and decryption module using XSalsa20-Poly1305."""
import base64
from typing import Tuple

from nacl.public import PrivateKey, PublicKey, Box
from nacl.signing import VerifyKey

from client.utils.logger import get_logger

logger = get_logger(__name__)


class EncryptionManager:
    """Handles message encryption and decryption using XSalsa20-Poly1305."""

    @staticmethod
    def convert_ed25519_to_curve25519(ed25519_key: VerifyKey) -> PublicKey:
        """Convert ed25519 public key to curve25519 for encryption.

        Ed25519 is used for signatures, but for encryption we need Curve25519.
        PyNaCl handles this conversion internally.

        Args:
            ed25519_key: Ed25519 public key (VerifyKey).

        Returns:
            Curve25519 public key for encryption.
        """
        # Convert ed25519 verify key to curve25519 public key
        # PyNaCl's Box can work directly with ed25519 keys
        # But we need to use the to_curve25519_public_key() method
        curve25519_public = ed25519_key.to_curve25519_public_key()
        return curve25519_public

    @staticmethod
    def encrypt_message(
        plaintext: str,
        sender_private_key: PrivateKey,
        recipient_public_key: PublicKey
    ) -> Tuple[bytes, bytes]:
        """Encrypt a message using XSalsa20-Poly1305.

        Args:
            plaintext: Plain text message to encrypt.
            sender_private_key: Sender's private key for ECDH.
            recipient_public_key: Recipient's public key for ECDH.

        Returns:
            Tuple of (encrypted_message, nonce).
        """
        # Create a Box for encryption using ECDH key exchange
        box = Box(sender_private_key, recipient_public_key)

        # Encrypt the message
        # Box.encrypt automatically generates a random nonce
        plaintext_bytes = plaintext.encode("utf-8")
        encrypted = box.encrypt(plaintext_bytes)

        # The encrypted message contains nonce + ciphertext
        # We need to extract them separately
        # First 24 bytes are the nonce, rest is ciphertext
        nonce = encrypted[:24]
        ciphertext = encrypted[24:]

        logger.debug(f"Message encrypted successfully, nonce: {base64.b64encode(nonce).decode()}")

        return ciphertext, nonce

    @staticmethod
    def decrypt_message(
        ciphertext: bytes,
        nonce: bytes,
        recipient_private_key: PrivateKey,
        sender_public_key: PublicKey
    ) -> str:
        """Decrypt a message using XSalsa20-Poly1305.

        Args:
            ciphertext: Encrypted message bytes.
            nonce: Nonce used for encryption.
            recipient_private_key: Recipient's private key for ECDH.
            sender_public_key: Sender's public key for ECDH.

        Returns:
            Decrypted plain text message.
        """
        # Create a Box for decryption
        box = Box(recipient_private_key, sender_public_key)

        # Reconstruct the encrypted message format (nonce + ciphertext)
        encrypted = nonce + ciphertext

        # Decrypt the message
        plaintext_bytes = box.decrypt(encrypted)
        plaintext = plaintext_bytes.decode("utf-8")

        logger.debug("Message decrypted successfully")

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
