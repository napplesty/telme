"""Shared test fixtures for telme project tests."""
import base64
import hashlib
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from nacl.public import Box
from nacl.signing import SigningKey

from server.app import create_app


@pytest.fixture
def app():
    """Create a fresh FastAPI application instance for testing."""
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    """Create an async HTTP test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def generate_keypair():
    """Factory fixture to generate a new Ed25519 key pair.

    Returns a dict with:
      - signing_key: SigningKey instance
      - verify_key: VerifyKey instance
      - public_key_bytes: raw 32-byte public key
      - public_key_b64: base64-encoded public key
      - user_id: SHA256 hex digest of the public key bytes
      - signature_bytes: signature of the public key (proving ownership)
      - signature_b64: base64-encoded signature
    """

    def _generate():
        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        public_key_bytes = bytes(verify_key)
        public_key_b64 = base64.b64encode(public_key_bytes).decode("utf-8")
        user_id = hashlib.sha256(public_key_bytes).hexdigest()

        # Sign the public key to prove ownership
        signature_bytes = signing_key.sign(public_key_bytes).signature
        signature_b64 = base64.b64encode(signature_bytes).decode("utf-8")

        return {
            "signing_key": signing_key,
            "verify_key": verify_key,
            "public_key_bytes": public_key_bytes,
            "public_key_b64": public_key_b64,
            "user_id": user_id,
            "signature_bytes": signature_bytes,
            "signature_b64": signature_b64,
        }

    return _generate


@pytest_asyncio.fixture
async def registered_user(client, generate_keypair):
    """Register a single user on the test server and return user info + keys."""
    keys = generate_keypair()
    timestamp = datetime.now().isoformat()

    response = await client.post(
        "/api/v1/keys/register",
        json={
            "public_key": keys["public_key_b64"],
            "signature": keys["signature_b64"],
            "timestamp": timestamp,
        },
    )
    assert response.status_code == 201
    data = response.json()

    return {
        **keys,
        "user_id": data["user_id"],
        "registered_at": data["registered_at"],
    }


@pytest_asyncio.fixture
async def alice_and_bob(client, generate_keypair):
    """Register two users (alice and bob) for messaging tests."""
    users = {}
    for name in ("alice", "bob"):
        keys = generate_keypair()
        timestamp = datetime.now().isoformat()

        response = await client.post(
            "/api/v1/keys/register",
            json={
                "public_key": keys["public_key_b64"],
                "signature": keys["signature_b64"],
                "timestamp": timestamp,
            },
        )
        assert response.status_code == 201
        data = response.json()
        users[name] = {
            **keys,
            "user_id": data["user_id"],
            "registered_at": data["registered_at"],
        }

    return users


def make_encrypted_message(sender_signing_key: SigningKey, recipient_verify_key):
    """Create a properly encrypted message from sender to recipient.

    Returns a dict with encrypted_message, nonce, and signature (all base64).
    """
    # Convert Ed25519 keys to Curve25519 for encryption
    sender_private_curve = sender_signing_key.to_curve25519_private_key()
    recipient_public_curve = recipient_verify_key.to_curve25519_public_key()

    # Encrypt a test message
    box = Box(sender_private_curve, recipient_public_curve)
    plaintext = b"Hello, this is a test message!"
    encrypted = box.encrypt(plaintext)

    # Extract nonce (first 24 bytes) and ciphertext (rest)
    nonce = encrypted[:24]
    ciphertext = encrypted[24:]

    # Sign the encrypted message + nonce
    data_to_sign = ciphertext + nonce
    signature = sender_signing_key.sign(data_to_sign).signature

    return {
        "encrypted_message": base64.b64encode(ciphertext).decode("utf-8"),
        "nonce": base64.b64encode(nonce).decode("utf-8"),
        "signature": base64.b64encode(signature).decode("utf-8"),
    }


def decrypt_message(ciphertext_b64: str, nonce_b64: str, recipient_signing_key: SigningKey, sender_verify_key):
    """Decrypt a message received by recipient from sender.

    Returns the plaintext bytes.
    """
    recipient_private_curve = recipient_signing_key.to_curve25519_private_key()
    sender_public_curve = sender_verify_key.to_curve25519_public_key()

    ciphertext = base64.b64decode(ciphertext_b64)
    nonce = base64.b64decode(nonce_b64)

    box = Box(recipient_private_curve, sender_public_curve)
    plaintext = box.decrypt(nonce + ciphertext)
    return plaintext
