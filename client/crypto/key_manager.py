"""Key management module for ed25519 keys."""
import base64
import hashlib
from pathlib import Path
from typing import Optional

from nacl.signing import SigningKey, VerifyKey

from client.config import config
from client.utils.logger import get_logger

logger = get_logger(__name__)


class KeyManager:
    """Manages ed25519 key generation, storage, and retrieval."""

    def __init__(self, keys_dir: Optional[Path] = None):
        """Initialize key manager.

        Args:
            keys_dir: Directory to store keys. Defaults to config.KEYS_DIR.
        """
        self.keys_dir = keys_dir or config.KEYS_DIR
        self.keys_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._signing_key: Optional[SigningKey] = None
        self._public_key: Optional[VerifyKey] = None

    @property
    def has_keys(self) -> bool:
        """Check if keys already exist."""
        private_key_path = self.keys_dir / "private_key.bin"
        return private_key_path.exists()

    def generate_keys(self) -> None:
        """Generate a new ed25519 key pair."""
        logger.info("Generating new ed25519 key pair")

        # Generate signing key (includes both private and public key)
        signing_key = SigningKey.generate()

        # Save private key with restrictive permissions
        private_key_path = self.keys_dir / "private_key.bin"
        private_key_path.write_bytes(bytes(signing_key))
        private_key_path.chmod(0o600)

        # Save public key
        public_key_path = self.keys_dir / "public_key.bin"
        public_key_path.write_bytes(bytes(signing_key.verify_key))
        public_key_path.chmod(0o644)

        logger.info(f"Keys generated and saved to {self.keys_dir}")

    def load_keys(self) -> None:
        """Load existing keys from disk."""
        if not self.has_keys:
            raise FileNotFoundError("No keys found. Please generate keys first.")

        private_key_path = self.keys_dir / "private_key.bin"

        # Load private key
        private_key_bytes = private_key_path.read_bytes()
        self._signing_key = SigningKey(private_key_bytes)
        self._public_key = self._signing_key.verify_key

        logger.info("Keys loaded successfully")

    def get_or_create_keys(self) -> None:
        """Load existing keys or create new ones if they don't exist."""
        if self.has_keys:
            logger.info("Loading existing keys")
            self.load_keys()
        else:
            logger.info("No existing keys found, generating new ones")
            self.generate_keys()
            self.load_keys()

    @property
    def signing_key(self) -> SigningKey:
        """Get the signing key (private key)."""
        if self._signing_key is None:
            raise RuntimeError("Keys not loaded. Call load_keys() first.")
        return self._signing_key

    @property
    def public_key(self) -> VerifyKey:
        """Get the public key (verify key)."""
        if self._public_key is None:
            raise RuntimeError("Keys not loaded. Call load_keys() first.")
        return self._public_key

    @property
    def public_key_bytes(self) -> bytes:
        """Get public key as bytes."""
        return bytes(self.public_key)

    @property
    def public_key_base64(self) -> str:
        """Get public key as base64-encoded string."""
        return base64.b64encode(self.public_key_bytes).decode("utf-8")

    @property
    def user_id(self) -> str:
        """Get user ID (hash of public key)."""
        return hashlib.sha256(self.public_key_bytes).hexdigest()

    @staticmethod
    def base64_to_public_key(public_key_base64: str) -> VerifyKey:
        """Convert base64-encoded public key to VerifyKey object.

        Args:
            public_key_base64: Base64-encoded public key string.

        Returns:
            VerifyKey object.

        Raises:
            ValueError: If the string is not valid base64 or not a valid 32-byte ed25519 key.
        """
        try:
            public_key_bytes = base64.b64decode(public_key_base64)
        except Exception:
            raise ValueError("Invalid public key: not valid base64 encoding")
        if len(public_key_bytes) != 32:
            raise ValueError(
                f"Invalid public key: expected 32 bytes, got {len(public_key_bytes)}"
            )
        return VerifyKey(public_key_bytes)

    @staticmethod
    def user_id_from_public_key(public_key: VerifyKey) -> str:
        """Generate user ID from public key.

        Args:
            public_key: VerifyKey object.

        Returns:
            User ID (SHA256 hash of public key).
        """
        return hashlib.sha256(bytes(public_key)).hexdigest()

    def delete_keys(self) -> None:
        """Delete all keys from disk. Use with caution!"""
        logger.warning("Deleting all keys from disk")

        private_key_path = self.keys_dir / "private_key.bin"
        public_key_path = self.keys_dir / "public_key.bin"

        if private_key_path.exists():
            private_key_path.unlink()
        if public_key_path.exists():
            public_key_path.unlink()

        self._signing_key = None
        self._public_key = None

        logger.info("Keys deleted successfully")
