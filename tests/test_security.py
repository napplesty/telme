"""Security tests for the Telme server and client crypto."""
import asyncio
import base64
import hashlib
import os
from datetime import datetime, timedelta

import pytest
import httpx
from httpx import ASGITransport
from nacl.public import Box, PrivateKey, PublicKey
from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import CryptoError

from client.crypto.encryption import EncryptionManager
from client.crypto.signature import SignatureManager
from server.app import create_app
from server.config import config


def _generate_user_credentials():
    """Generate a valid user key pair and registration payload."""
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    pubkey_bytes = bytes(verify_key)
    pubkey_b64 = base64.b64encode(pubkey_bytes).decode()
    signature = signing_key.sign(pubkey_bytes).signature
    signature_b64 = base64.b64encode(signature).decode()
    user_id = hashlib.sha256(pubkey_bytes).hexdigest()
    return {
        "signing_key": signing_key,
        "verify_key": verify_key,
        "pubkey_bytes": pubkey_bytes,
        "pubkey_b64": pubkey_b64,
        "signature_b64": signature_b64,
        "user_id": user_id,
    }


def _make_register_payload(creds):
    """Build registration JSON payload."""
    return {
        "public_key": creds["pubkey_b64"],
        "signature": creds["signature_b64"],
        "timestamp": datetime.now().isoformat(),
    }


def _make_send_payload(sender_creds, recipient_id, size=64, timestamp=None):
    """Build message send JSON payload."""
    encrypted = base64.b64encode(os.urandom(size)).decode()
    nonce = base64.b64encode(os.urandom(24)).decode()
    signature = base64.b64encode(os.urandom(64)).decode()
    ts = timestamp if timestamp else datetime.now().isoformat()
    return {
        "sender_id": sender_creds["user_id"],
        "recipient_id": recipient_id,
        "encrypted_message": encrypted,
        "nonce": nonce,
        "signature": signature,
        "timestamp": ts,
    }


@pytest.fixture
def app():
    """Create a fresh app instance for each test."""
    return create_app()


@pytest.fixture
def transport(app):
    """Create ASGI transport for httpx."""
    return ASGITransport(app=app)


@pytest.fixture
def base_url():
    return "http://testserver"


# =============================================================================
# Encryption Integrity Tests
# =============================================================================


class TestEncryptionIntegrity:
    """Test that E2E encryption is robust."""

    @pytest.mark.security
    def test_alice_bob_encrypt_decrypt(self):
        """Alice encrypts a message for Bob; Bob can decrypt it."""
        alice_signing = SigningKey.generate()
        bob_signing = SigningKey.generate()

        # Convert to Curve25519 keys for encryption
        alice_private = alice_signing.to_curve25519_private_key()
        bob_private = bob_signing.to_curve25519_private_key()
        alice_public = alice_private.public_key
        bob_public = bob_private.public_key

        plaintext = "Hello Bob, this is a secret message!"
        ciphertext, nonce = EncryptionManager.encrypt_message(
            plaintext, alice_private, bob_public
        )

        # Bob decrypts
        decrypted = EncryptionManager.decrypt_message(
            ciphertext, nonce, bob_private, alice_public
        )
        assert decrypted == plaintext

    @pytest.mark.security
    def test_eve_cannot_decrypt(self):
        """A third party (Eve) cannot decrypt messages between Alice and Bob."""
        alice_signing = SigningKey.generate()
        bob_signing = SigningKey.generate()
        eve_signing = SigningKey.generate()

        alice_private = alice_signing.to_curve25519_private_key()
        bob_private = bob_signing.to_curve25519_private_key()
        eve_private = eve_signing.to_curve25519_private_key()
        alice_public = alice_private.public_key
        bob_public = bob_private.public_key

        plaintext = "Secret message for Bob only"
        ciphertext, nonce = EncryptionManager.encrypt_message(
            plaintext, alice_private, bob_public
        )

        # Eve tries to decrypt with her key
        with pytest.raises(CryptoError):
            EncryptionManager.decrypt_message(
                ciphertext, nonce, eve_private, alice_public
            )

    @pytest.mark.security
    def test_tampered_ciphertext_fails(self):
        """Tampering with ciphertext causes decryption failure."""
        alice_signing = SigningKey.generate()
        bob_signing = SigningKey.generate()

        alice_private = alice_signing.to_curve25519_private_key()
        bob_private = bob_signing.to_curve25519_private_key()
        alice_public = alice_private.public_key
        bob_public = bob_private.public_key

        plaintext = "Do not tamper with this"
        ciphertext, nonce = EncryptionManager.encrypt_message(
            plaintext, alice_private, bob_public
        )

        # Tamper with ciphertext by flipping a byte
        tampered = bytearray(ciphertext)
        tampered[0] ^= 0xFF
        tampered = bytes(tampered)

        with pytest.raises(CryptoError):
            EncryptionManager.decrypt_message(tampered, nonce, bob_private, alice_public)

    @pytest.mark.security
    def test_tampered_nonce_fails(self):
        """Tampering with nonce causes decryption failure."""
        alice_signing = SigningKey.generate()
        bob_signing = SigningKey.generate()

        alice_private = alice_signing.to_curve25519_private_key()
        bob_private = bob_signing.to_curve25519_private_key()
        alice_public = alice_private.public_key
        bob_public = bob_private.public_key

        plaintext = "Protected by nonce integrity"
        ciphertext, nonce = EncryptionManager.encrypt_message(
            plaintext, alice_private, bob_public
        )

        # Tamper with nonce
        tampered_nonce = bytearray(nonce)
        tampered_nonce[0] ^= 0xFF
        tampered_nonce = bytes(tampered_nonce)

        with pytest.raises(CryptoError):
            EncryptionManager.decrypt_message(
                ciphertext, tampered_nonce, bob_private, alice_public
            )

    @pytest.mark.security
    def test_wrong_sender_key_fails(self):
        """Using wrong sender key causes decryption failure."""
        alice_signing = SigningKey.generate()
        bob_signing = SigningKey.generate()
        mallory_signing = SigningKey.generate()

        alice_private = alice_signing.to_curve25519_private_key()
        bob_private = bob_signing.to_curve25519_private_key()
        mallory_private = mallory_signing.to_curve25519_private_key()
        bob_public = bob_private.public_key
        mallory_public = mallory_private.public_key

        plaintext = "From Alice"
        ciphertext, nonce = EncryptionManager.encrypt_message(
            plaintext, alice_private, bob_public
        )

        # Bob tries to decrypt thinking it's from Mallory
        with pytest.raises(CryptoError):
            EncryptionManager.decrypt_message(
                ciphertext, nonce, bob_private, mallory_public
            )


# =============================================================================
# Signature Verification Tests
# =============================================================================


class TestSignatureVerification:
    """Test digital signature integrity."""

    @pytest.mark.security
    def test_valid_signature_passes(self):
        """A correctly signed message passes verification."""
        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        message = "This is authentic"

        signature = SignatureManager.sign_message(message, signing_key)
        assert SignatureManager.verify_signature(message, signature, verify_key)

    @pytest.mark.security
    def test_modified_message_fails(self):
        """Modified message fails signature verification."""
        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        message = "Original message"

        signature = SignatureManager.sign_message(message, signing_key)
        assert not SignatureManager.verify_signature(
            "Tampered message", signature, verify_key
        )

    @pytest.mark.security
    def test_wrong_key_fails(self):
        """Signature from one key fails verification with another key."""
        signing_key = SigningKey.generate()
        other_key = SigningKey.generate()
        message = "Signed by first key"

        signature = SignatureManager.sign_message(message, signing_key)
        # Verify with different key
        assert not SignatureManager.verify_signature(
            message, signature, other_key.verify_key
        )

    @pytest.mark.security
    def test_signature_from_different_keypair_fails(self):
        """Signature generated by a different key pair fails."""
        alice_key = SigningKey.generate()
        bob_key = SigningKey.generate()
        message = "Hello"

        # Alice signs
        alice_sig = SignatureManager.sign_message(message, alice_key)
        # Verify with Bob's key
        assert not SignatureManager.verify_signature(
            message, alice_sig, bob_key.verify_key
        )


# =============================================================================
# Key Registration Security Tests
# =============================================================================


class TestKeyRegistrationSecurity:
    """Test key registration API security."""

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self, transport, base_url):
        """Registration with random bytes as signature is rejected."""
        signing_key = SigningKey.generate()
        pubkey_bytes = bytes(signing_key.verify_key)
        pubkey_b64 = base64.b64encode(pubkey_bytes).decode()
        # Random bytes as signature (invalid)
        bad_signature = base64.b64encode(os.urandom(64)).decode()

        payload = {
            "public_key": pubkey_b64,
            "signature": bad_signature,
            "timestamp": datetime.now().isoformat(),
        }

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/api/v1/keys/register", json=payload)
            assert resp.status_code == 400

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_mismatched_key_signature_rejected(self, transport, base_url):
        """Registration with signature from different key pair is rejected."""
        key_a = SigningKey.generate()
        key_b = SigningKey.generate()
        pubkey_a_bytes = bytes(key_a.verify_key)
        pubkey_a_b64 = base64.b64encode(pubkey_a_bytes).decode()
        # Sign key_a's pubkey with key_b (mismatched)
        sig_from_b = key_b.sign(pubkey_a_bytes).signature
        sig_b64 = base64.b64encode(sig_from_b).decode()

        payload = {
            "public_key": pubkey_a_b64,
            "signature": sig_b64,
            "timestamp": datetime.now().isoformat(),
        }

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/api/v1/keys/register", json=payload)
            assert resp.status_code == 400

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_wrong_length_public_key_rejected(self, transport, base_url):
        """Registration with wrong-length public key is rejected."""
        # 16 bytes instead of 32
        bad_pubkey = base64.b64encode(os.urandom(16)).decode()
        fake_sig = base64.b64encode(os.urandom(64)).decode()

        payload = {
            "public_key": bad_pubkey,
            "signature": fake_sig,
            "timestamp": datetime.now().isoformat(),
        }

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/api/v1/keys/register", json=payload)
            assert resp.status_code == 400

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_non_base64_data_rejected(self, transport, base_url):
        """Registration with non-base64 data is rejected."""
        payload = {
            "public_key": "not-valid-base64!!!@@@",
            "signature": "also-not-valid!!!@@@",
            "timestamp": datetime.now().isoformat(),
        }

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/api/v1/keys/register", json=payload)
            assert resp.status_code == 400


# =============================================================================
# Replay Attack Prevention Tests
# =============================================================================


class TestReplayAttackPrevention:
    """Test timestamp-based replay attack prevention."""

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_old_timestamp_rejected(self, transport, base_url):
        """Message with timestamp > 5 minutes in the past is rejected."""
        sender = _generate_user_credentials()
        recipient = _generate_user_credentials()

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(sender)
            )
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(recipient)
            )

            old_timestamp = (datetime.now() - timedelta(minutes=6)).isoformat()
            payload = _make_send_payload(
                sender, recipient["user_id"], timestamp=old_timestamp
            )
            resp = await client.post("/api/v1/messages/send", json=payload)
            assert resp.status_code == 400
            assert "old" in resp.json()["detail"].lower() or "replay" in resp.json()["detail"].lower()

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_future_timestamp_rejected(self, transport, base_url):
        """Message with timestamp > 5 minutes in the future is rejected."""
        sender = _generate_user_credentials()
        recipient = _generate_user_credentials()

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(sender)
            )
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(recipient)
            )

            future_timestamp = (datetime.now() + timedelta(minutes=6)).isoformat()
            payload = _make_send_payload(
                sender, recipient["user_id"], timestamp=future_timestamp
            )
            resp = await client.post("/api/v1/messages/send", json=payload)
            assert resp.status_code == 400
            assert "future" in resp.json()["detail"].lower()

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_boundary_timestamp_accepted(self, transport, base_url):
        """Message at boundary (4.9 minutes old) is still accepted."""
        sender = _generate_user_credentials()
        recipient = _generate_user_credentials()

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(sender)
            )
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(recipient)
            )

            # 4.9 minutes = 294 seconds, within the 300 second tolerance
            boundary_timestamp = (
                datetime.now() - timedelta(seconds=294)
            ).isoformat()
            payload = _make_send_payload(
                sender, recipient["user_id"], timestamp=boundary_timestamp
            )
            resp = await client.post("/api/v1/messages/send", json=payload)
            assert resp.status_code == 201

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_registration_old_timestamp_rejected(self, transport, base_url):
        """Key registration with old timestamp is rejected."""
        creds = _generate_user_credentials()
        payload = _make_register_payload(creds)
        payload["timestamp"] = (datetime.now() - timedelta(minutes=6)).isoformat()

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/api/v1/keys/register", json=payload)
            assert resp.status_code == 400


# =============================================================================
# Input Validation Tests
# =============================================================================


class TestInputValidation:
    """Test input validation rejects malformed requests."""

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_invalid_user_id_wrong_length(self, transport, base_url):
        """User ID with wrong length is rejected."""
        sender = _generate_user_credentials()
        recipient = _generate_user_credentials()

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(sender)
            )
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(recipient)
            )

            # Wrong length sender_id
            payload = _make_send_payload(sender, recipient["user_id"])
            payload["sender_id"] = "abc123"  # Too short
            resp = await client.post("/api/v1/messages/send", json=payload)
            assert resp.status_code == 400

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_invalid_user_id_non_hex(self, transport, base_url):
        """User ID with non-hex characters is rejected."""
        sender = _generate_user_credentials()
        recipient = _generate_user_credentials()

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(sender)
            )
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(recipient)
            )

            payload = _make_send_payload(sender, recipient["user_id"])
            # 64 chars but non-hex
            payload["sender_id"] = "g" * 64
            resp = await client.post("/api/v1/messages/send", json=payload)
            assert resp.status_code == 400

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_invalid_user_id_empty(self, transport, base_url):
        """Empty user ID is rejected."""
        sender = _generate_user_credentials()
        recipient = _generate_user_credentials()

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(sender)
            )
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(recipient)
            )

            payload = _make_send_payload(sender, recipient["user_id"])
            payload["sender_id"] = ""
            resp = await client.post("/api/v1/messages/send", json=payload)
            assert resp.status_code == 400

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_oversized_message_rejected(self, transport, base_url):
        """Message exceeding 1MB is rejected."""
        sender = _generate_user_credentials()
        recipient = _generate_user_credentials()

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(sender)
            )
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(recipient)
            )

            # 2MB message payload
            oversized = base64.b64encode(os.urandom(2 * 1024 * 1024)).decode()
            payload = {
                "sender_id": sender["user_id"],
                "recipient_id": recipient["user_id"],
                "encrypted_message": oversized,
                "nonce": base64.b64encode(os.urandom(24)).decode(),
                "signature": base64.b64encode(os.urandom(64)).decode(),
                "timestamp": datetime.now().isoformat(),
            }
            resp = await client.post("/api/v1/messages/send", json=payload)
            assert resp.status_code == 400

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_invalid_base64_in_fields_rejected(self, transport, base_url):
        """Invalid base64 in message fields is rejected."""
        sender = _generate_user_credentials()
        recipient = _generate_user_credentials()

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(sender)
            )
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(recipient)
            )

            # Invalid base64 in encrypted_message
            payload = {
                "sender_id": sender["user_id"],
                "recipient_id": recipient["user_id"],
                "encrypted_message": "!!!not-base64!!!",
                "nonce": base64.b64encode(os.urandom(24)).decode(),
                "signature": base64.b64encode(os.urandom(64)).decode(),
                "timestamp": datetime.now().isoformat(),
            }
            resp = await client.post("/api/v1/messages/send", json=payload)
            assert resp.status_code == 400

            # Invalid base64 in nonce
            payload["encrypted_message"] = base64.b64encode(os.urandom(64)).decode()
            payload["nonce"] = "!!!not-base64!!!"
            resp = await client.post("/api/v1/messages/send", json=payload)
            assert resp.status_code == 400

            # Invalid base64 in signature
            payload["nonce"] = base64.b64encode(os.urandom(24)).decode()
            payload["signature"] = "!!!not-base64!!!"
            resp = await client.post("/api/v1/messages/send", json=payload)
            assert resp.status_code == 400


# =============================================================================
# Message Isolation Tests
# =============================================================================


class TestMessageIsolation:
    """Test that messages are isolated between users."""

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_user_cannot_pull_others_messages(self, transport, base_url):
        """User A cannot pull User B's messages."""
        sender = _generate_user_credentials()
        user_a = _generate_user_credentials()
        user_b = _generate_user_credentials()

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            # Register all users
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(sender)
            )
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(user_a)
            )
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(user_b)
            )

            # Send message to user_b only
            payload = _make_send_payload(sender, user_b["user_id"])
            resp = await client.post("/api/v1/messages/send", json=payload)
            assert resp.status_code == 201

            # User A tries to pull - should get nothing
            pull_payload = {
                "user_id": user_a["user_id"],
                "acked_seq": 0,
                "limit": 100,
            }
            resp = await client.post("/api/v1/messages/pull", json=pull_payload)
            assert resp.status_code == 200
            assert len(resp.json()["messages"]) == 0

            # User B pulls - should get the message
            pull_payload["user_id"] = user_b["user_id"]
            resp = await client.post("/api/v1/messages/pull", json=pull_payload)
            assert resp.status_code == 200
            assert len(resp.json()["messages"]) == 1

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_messages_delivered_only_to_recipient(self, transport, base_url):
        """Messages are delivered only to their intended recipient."""
        sender = _generate_user_credentials()
        recipients = [_generate_user_credentials() for _ in range(5)]

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            # Register all
            await client.post(
                "/api/v1/keys/register", json=_make_register_payload(sender)
            )
            for r in recipients:
                await client.post(
                    "/api/v1/keys/register", json=_make_register_payload(r)
                )

            # Send one message to recipient[0] only
            payload = _make_send_payload(sender, recipients[0]["user_id"])
            resp = await client.post("/api/v1/messages/send", json=payload)
            assert resp.status_code == 201

            # Only recipient[0] should have the message
            for i, r in enumerate(recipients):
                pull_payload = {
                    "user_id": r["user_id"],
                    "acked_seq": 0,
                    "limit": 100,
                }
                resp = await client.post("/api/v1/messages/pull", json=pull_payload)
                assert resp.status_code == 200
                messages = resp.json()["messages"]
                if i == 0:
                    assert len(messages) == 1
                else:
                    assert len(messages) == 0


# =============================================================================
# Key Isolation Tests
# =============================================================================


class TestKeyIsolation:
    """Test key isolation properties."""

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_different_keys_different_user_ids(self, transport, base_url):
        """Two users with different keys get different user_ids."""
        user_a = _generate_user_credentials()
        user_b = _generate_user_credentials()

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            resp_a = await client.post(
                "/api/v1/keys/register", json=_make_register_payload(user_a)
            )
            resp_b = await client.post(
                "/api/v1/keys/register", json=_make_register_payload(user_b)
            )

            assert resp_a.status_code == 201
            assert resp_b.status_code == 201
            assert resp_a.json()["user_id"] != resp_b.json()["user_id"]

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_same_key_same_user_id(self, transport, base_url):
        """Re-registering the same key returns the same user_id."""
        creds = _generate_user_credentials()

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            resp1 = await client.post(
                "/api/v1/keys/register", json=_make_register_payload(creds)
            )
            resp2 = await client.post(
                "/api/v1/keys/register", json=_make_register_payload(creds)
            )

            assert resp1.status_code == 201
            assert resp2.status_code == 201
            assert resp1.json()["user_id"] == resp2.json()["user_id"]
