"""Functional tests for the telme server API."""
import base64
import hashlib
from datetime import datetime, timedelta

import pytest
from nacl.signing import SigningKey

from tests.conftest import decrypt_message, make_encrypted_message


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """GET /health should return status healthy."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert data["version"] == "0.1.0"


# ---------------------------------------------------------------------------
# Key registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_key_valid(client, generate_keypair):
    """POST /api/v1/keys/register with valid data should return 201."""
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
    assert data["user_id"] == keys["user_id"]
    assert "registered_at" in data


@pytest.mark.asyncio
async def test_register_key_invalid_signature(client, generate_keypair):
    """POST /api/v1/keys/register with an invalid signature should return 400."""
    keys = generate_keypair()
    # Create a different signing key to produce a wrong signature
    wrong_key = SigningKey.generate()
    wrong_signature = wrong_key.sign(keys["public_key_bytes"]).signature
    wrong_signature_b64 = base64.b64encode(wrong_signature).decode("utf-8")

    response = await client.post(
        "/api/v1/keys/register",
        json={
            "public_key": keys["public_key_b64"],
            "signature": wrong_signature_b64,
            "timestamp": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_key_invalid_base64(client):
    """POST /api/v1/keys/register with invalid base64 should return 400."""
    response = await client.post(
        "/api/v1/keys/register",
        json={
            "public_key": "not-valid-base64!!!",
            "signature": "also-not-valid!!!",
            "timestamp": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_key_missing_fields(client):
    """POST /api/v1/keys/register with missing fields should return 422."""
    response = await client.post(
        "/api/v1/keys/register",
        json={"public_key": "abc"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Key retrieval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_key_registered_user(client, registered_user):
    """GET /api/v1/keys/{user_id} for a registered user returns public key."""
    user_id = registered_user["user_id"]
    response = await client.get(f"/api/v1/keys/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id
    assert data["public_key"] == registered_user["public_key_b64"]


@pytest.mark.asyncio
async def test_get_key_nonexistent_user(client):
    """GET /api/v1/keys/{user_id} for unknown user returns 404."""
    fake_user_id = "a" * 64
    response = await client.get(f"/api/v1/keys/{fake_user_id}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Message send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_valid(client, alice_and_bob):
    """POST /api/v1/messages/send with valid payload should return 201."""
    alice = alice_and_bob["alice"]
    bob = alice_and_bob["bob"]

    msg_payload = make_encrypted_message(
        sender_signing_key=alice["signing_key"],
        recipient_verify_key=bob["verify_key"],
    )

    response = await client.post(
        "/api/v1/messages/send",
        json={
            "sender_id": alice["user_id"],
            "recipient_id": bob["user_id"],
            "encrypted_message": msg_payload["encrypted_message"],
            "nonce": msg_payload["nonce"],
            "signature": msg_payload["signature"],
            "timestamp": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sender_id"] == alice["user_id"]
    assert data["recipient_id"] == bob["user_id"]
    assert data["status"] == "queued"
    assert "message_id" in data
    assert "server_seq" in data


@pytest.mark.asyncio
async def test_send_message_unregistered_sender(client, alice_and_bob):
    """POST /api/v1/messages/send with unregistered sender returns 404."""
    bob = alice_and_bob["bob"]
    fake_sender_id = "b" * 64

    response = await client.post(
        "/api/v1/messages/send",
        json={
            "sender_id": fake_sender_id,
            "recipient_id": bob["user_id"],
            "encrypted_message": base64.b64encode(b"x" * 32).decode(),
            "nonce": base64.b64encode(b"n" * 24).decode(),
            "signature": base64.b64encode(b"s" * 64).decode(),
            "timestamp": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 404
    assert "Sender" in response.json()["detail"]


@pytest.mark.asyncio
async def test_send_message_unregistered_recipient(client, alice_and_bob):
    """POST /api/v1/messages/send with unregistered recipient returns 404."""
    alice = alice_and_bob["alice"]
    fake_recipient_id = "c" * 64

    response = await client.post(
        "/api/v1/messages/send",
        json={
            "sender_id": alice["user_id"],
            "recipient_id": fake_recipient_id,
            "encrypted_message": base64.b64encode(b"x" * 32).decode(),
            "nonce": base64.b64encode(b"n" * 24).decode(),
            "signature": base64.b64encode(b"s" * 64).decode(),
            "timestamp": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 404
    assert "Recipient" in response.json()["detail"]


@pytest.mark.asyncio
async def test_send_message_invalid_base64(client, alice_and_bob):
    """POST /api/v1/messages/send with invalid base64 fields returns 400."""
    alice = alice_and_bob["alice"]
    bob = alice_and_bob["bob"]

    response = await client.post(
        "/api/v1/messages/send",
        json={
            "sender_id": alice["user_id"],
            "recipient_id": bob["user_id"],
            "encrypted_message": "not!!valid!!base64",
            "nonce": base64.b64encode(b"n" * 24).decode(),
            "signature": base64.b64encode(b"s" * 64).decode(),
            "timestamp": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_send_message_oversized(client, alice_and_bob):
    """POST /api/v1/messages/send with oversized message returns 400."""
    alice = alice_and_bob["alice"]
    bob = alice_and_bob["bob"]

    # 2 MB payload exceeds the 1 MB limit
    big_payload = base64.b64encode(b"x" * (2 * 1024 * 1024)).decode()

    response = await client.post(
        "/api/v1/messages/send",
        json={
            "sender_id": alice["user_id"],
            "recipient_id": bob["user_id"],
            "encrypted_message": big_payload,
            "nonce": base64.b64encode(b"n" * 24).decode(),
            "signature": base64.b64encode(b"s" * 64).decode(),
            "timestamp": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_send_message_expired_timestamp(client, alice_and_bob):
    """POST /api/v1/messages/send with an old timestamp returns 400."""
    alice = alice_and_bob["alice"]
    bob = alice_and_bob["bob"]

    msg_payload = make_encrypted_message(
        sender_signing_key=alice["signing_key"],
        recipient_verify_key=bob["verify_key"],
    )

    # Timestamp 10 minutes in the past (exceeds 5-minute tolerance)
    old_timestamp = (datetime.now() - timedelta(minutes=10)).isoformat()

    response = await client.post(
        "/api/v1/messages/send",
        json={
            "sender_id": alice["user_id"],
            "recipient_id": bob["user_id"],
            "encrypted_message": msg_payload["encrypted_message"],
            "nonce": msg_payload["nonce"],
            "signature": msg_payload["signature"],
            "timestamp": old_timestamp,
        },
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Message pull
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pull_messages_valid(client, alice_and_bob):
    """POST /api/v1/messages/pull after sending a message returns it."""
    alice = alice_and_bob["alice"]
    bob = alice_and_bob["bob"]

    # Send a message from alice to bob
    msg_payload = make_encrypted_message(
        sender_signing_key=alice["signing_key"],
        recipient_verify_key=bob["verify_key"],
    )
    await client.post(
        "/api/v1/messages/send",
        json={
            "sender_id": alice["user_id"],
            "recipient_id": bob["user_id"],
            "encrypted_message": msg_payload["encrypted_message"],
            "nonce": msg_payload["nonce"],
            "signature": msg_payload["signature"],
            "timestamp": datetime.now().isoformat(),
        },
    )

    # Pull messages for bob
    response = await client.post(
        "/api/v1/messages/pull",
        json={
            "user_id": bob["user_id"],
            "acked_seq": 0,
            "limit": 100,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["messages"]) == 1
    assert data["messages"][0]["sender_id"] == alice["user_id"]
    assert data["messages"][0]["recipient_id"] == bob["user_id"]
    assert data["last_seq"] == 1
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_pull_messages_pagination_with_acked_seq(client, alice_and_bob):
    """POST /api/v1/messages/pull with acked_seq skips acknowledged messages."""
    alice = alice_and_bob["alice"]
    bob = alice_and_bob["bob"]

    # Send 3 messages from alice to bob
    for _ in range(3):
        msg_payload = make_encrypted_message(
            sender_signing_key=alice["signing_key"],
            recipient_verify_key=bob["verify_key"],
        )
        await client.post(
            "/api/v1/messages/send",
            json={
                "sender_id": alice["user_id"],
                "recipient_id": bob["user_id"],
                "encrypted_message": msg_payload["encrypted_message"],
                "nonce": msg_payload["nonce"],
                "signature": msg_payload["signature"],
                "timestamp": datetime.now().isoformat(),
            },
        )

    # Pull with acked_seq=2 should only get seq 3
    response = await client.post(
        "/api/v1/messages/pull",
        json={
            "user_id": bob["user_id"],
            "acked_seq": 2,
            "limit": 100,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["messages"]) == 1
    assert data["messages"][0]["server_seq"] == 3
    assert data["last_seq"] == 3


@pytest.mark.asyncio
async def test_pull_messages_empty_queue(client, registered_user):
    """POST /api/v1/messages/pull with no messages returns empty list."""
    response = await client.post(
        "/api/v1/messages/pull",
        json={
            "user_id": registered_user["user_id"],
            "acked_seq": 0,
            "limit": 100,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["messages"] == []
    assert data["last_seq"] == 0
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_pull_messages_unregistered_user(client):
    """POST /api/v1/messages/pull for unregistered user returns 404."""
    fake_user_id = "d" * 64
    response = await client.post(
        "/api/v1/messages/pull",
        json={
            "user_id": fake_user_id,
            "acked_seq": 0,
            "limit": 100,
        },
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# End-to-end message flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_message_flow(client, alice_and_bob):
    """Full end-to-end: register -> send encrypted -> pull -> verify decryption."""
    alice = alice_and_bob["alice"]
    bob = alice_and_bob["bob"]

    # Alice sends an encrypted message to Bob
    msg_payload = make_encrypted_message(
        sender_signing_key=alice["signing_key"],
        recipient_verify_key=bob["verify_key"],
    )

    send_response = await client.post(
        "/api/v1/messages/send",
        json={
            "sender_id": alice["user_id"],
            "recipient_id": bob["user_id"],
            "encrypted_message": msg_payload["encrypted_message"],
            "nonce": msg_payload["nonce"],
            "signature": msg_payload["signature"],
            "timestamp": datetime.now().isoformat(),
        },
    )
    assert send_response.status_code == 201
    send_data = send_response.json()
    message_id = send_data["message_id"]

    # Bob pulls the message
    pull_response = await client.post(
        "/api/v1/messages/pull",
        json={
            "user_id": bob["user_id"],
            "acked_seq": 0,
            "limit": 100,
        },
    )
    assert pull_response.status_code == 200
    pull_data = pull_response.json()
    assert len(pull_data["messages"]) == 1

    pulled_msg = pull_data["messages"][0]
    assert pulled_msg["message_id"] == message_id
    assert pulled_msg["sender_id"] == alice["user_id"]

    # Bob decrypts the message
    plaintext = decrypt_message(
        ciphertext_b64=pulled_msg["encrypted_message"],
        nonce_b64=pulled_msg["nonce"],
        recipient_signing_key=bob["signing_key"],
        sender_verify_key=alice["verify_key"],
    )
    assert plaintext == b"Hello, this is a test message!"

    # Verify the signature on the pulled message
    ciphertext = base64.b64decode(pulled_msg["encrypted_message"])
    nonce = base64.b64decode(pulled_msg["nonce"])
    signature = base64.b64decode(pulled_msg["signature"])
    data_to_verify = ciphertext + nonce

    alice["verify_key"].verify(data_to_verify, signature)  # Raises if invalid
