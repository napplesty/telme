"""Stress and load tests for the Telme server."""
import asyncio
import base64
import hashlib
import os
import time
from datetime import datetime

import pytest
import httpx
from httpx import ASGITransport
from nacl.signing import SigningKey

from server.app import create_app
from server.config import config
from server.services.message_service import message_service


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


def _make_send_payload(sender_creds, recipient_id, size=64):
    """Build message send JSON payload with random encrypted content."""
    encrypted = base64.b64encode(os.urandom(size)).decode()
    nonce = base64.b64encode(os.urandom(24)).decode()
    signature = base64.b64encode(os.urandom(64)).decode()
    return {
        "sender_id": sender_creds["user_id"],
        "recipient_id": recipient_id,
        "encrypted_message": encrypted,
        "nonce": nonce,
        "signature": signature,
        "timestamp": datetime.now().isoformat(),
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
# Throughput benchmarks
# =============================================================================


@pytest.mark.stress
@pytest.mark.asyncio
async def test_concurrent_registrations_500(transport, base_url):
    """Register 500 users concurrently and measure throughput."""
    count = 500
    users = [_generate_user_credentials() for _ in range(count)]

    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:

        async def register(creds):
            payload = _make_register_payload(creds)
            return await client.post("/api/v1/keys/register", json=payload)

        t0 = time.perf_counter()
        responses = await asyncio.gather(*[register(u) for u in users])
        elapsed = time.perf_counter() - t0

    success_count = sum(1 for r in responses if r.status_code == 201)
    assert success_count == count, f"Only {success_count}/{count} registrations succeeded"

    throughput = count / elapsed
    print(f"\n  [PERF] {count} concurrent registrations: {elapsed:.3f}s ({throughput:.0f} reg/s)")


@pytest.mark.stress
@pytest.mark.asyncio
async def test_message_flood_5000(transport, base_url):
    """Send 5000 messages rapidly from one user to another, then pull all."""
    count = 5000
    sender = _generate_user_credentials()
    recipient = _generate_user_credentials()

    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        await client.post("/api/v1/keys/register", json=_make_register_payload(sender))
        await client.post("/api/v1/keys/register", json=_make_register_payload(recipient))

        # Send all messages concurrently
        send_tasks = [
            client.post("/api/v1/messages/send", json=_make_send_payload(sender, recipient["user_id"]))
            for _ in range(count)
        ]

        t0 = time.perf_counter()
        send_responses = await asyncio.gather(*send_tasks)
        send_elapsed = time.perf_counter() - t0

        send_success = sum(1 for r in send_responses if r.status_code == 201)
        assert send_success == count, f"Only {send_success}/{count} sends succeeded"

        # Pull all messages in batches
        t1 = time.perf_counter()
        all_messages = []
        acked_seq = 0
        while True:
            resp = await client.post("/api/v1/messages/pull", json={
                "user_id": recipient["user_id"],
                "acked_seq": acked_seq,
                "limit": 500,
            })
            assert resp.status_code == 200
            data = resp.json()
            all_messages.extend(data["messages"])
            acked_seq = data["last_seq"]
            if not data["has_more"]:
                break
        pull_elapsed = time.perf_counter() - t1

        assert len(all_messages) == count

    send_throughput = count / send_elapsed
    pull_throughput = count / pull_elapsed
    print(f"\n  [PERF] {count} messages send: {send_elapsed:.3f}s ({send_throughput:.0f} msg/s)")
    print(f"  [PERF] {count} messages pull: {pull_elapsed:.3f}s ({pull_throughput:.0f} msg/s)")


@pytest.mark.stress
@pytest.mark.asyncio
async def test_message_flood_10000(transport, base_url):
    """Send 10000 messages — stress test for large queues."""
    count = 10000
    sender = _generate_user_credentials()
    recipient = _generate_user_credentials()

    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        await client.post("/api/v1/keys/register", json=_make_register_payload(sender))
        await client.post("/api/v1/keys/register", json=_make_register_payload(recipient))

        # Send in batches of 2000 to avoid overwhelming the event loop
        t0 = time.perf_counter()
        total_sent = 0
        batch_size = 2000
        for batch_start in range(0, count, batch_size):
            batch_count = min(batch_size, count - batch_start)
            tasks = [
                client.post("/api/v1/messages/send", json=_make_send_payload(sender, recipient["user_id"]))
                for _ in range(batch_count)
            ]
            responses = await asyncio.gather(*tasks)
            total_sent += sum(1 for r in responses if r.status_code == 201)
        send_elapsed = time.perf_counter() - t0

        assert total_sent == count, f"Only {total_sent}/{count} sends succeeded"

        # Pull all
        t1 = time.perf_counter()
        all_messages = []
        acked_seq = 0
        while True:
            resp = await client.post("/api/v1/messages/pull", json={
                "user_id": recipient["user_id"],
                "acked_seq": acked_seq,
                "limit": 1000,
            })
            data = resp.json()
            all_messages.extend(data["messages"])
            acked_seq = data["last_seq"]
            if not data["has_more"]:
                break
        pull_elapsed = time.perf_counter() - t1

        assert len(all_messages) == count

    print(f"\n  [PERF] {count} messages send: {send_elapsed:.3f}s ({count/send_elapsed:.0f} msg/s)")
    print(f"  [PERF] {count} messages pull: {pull_elapsed:.3f}s ({count/pull_elapsed:.0f} msg/s)")


@pytest.mark.stress
@pytest.mark.asyncio
async def test_large_message_body(transport, base_url):
    """Send messages at and near the 1MB limit."""
    sender = _generate_user_credentials()
    recipient = _generate_user_credentials()

    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        await client.post("/api/v1/keys/register", json=_make_register_payload(sender))
        await client.post("/api/v1/keys/register", json=_make_register_payload(recipient))

        max_size = config.MAX_MESSAGE_SIZE

        # Exactly 1MB should succeed
        payload_at_limit = _make_send_payload(sender, recipient["user_id"], size=max_size)
        resp = await client.post("/api/v1/messages/send", json=payload_at_limit)
        assert resp.status_code == 201, f"At-limit message rejected: {resp.text}"

        # Just over 1MB should fail
        payload_over_limit = _make_send_payload(sender, recipient["user_id"], size=max_size + 1)
        resp = await client.post("/api/v1/messages/send", json=payload_over_limit)
        assert resp.status_code == 400, "Over-limit message should be rejected"

        # Just under 1MB should succeed
        payload_under_limit = _make_send_payload(sender, recipient["user_id"], size=max_size - 1)
        resp = await client.post("/api/v1/messages/send", json=payload_under_limit)
        assert resp.status_code == 201, f"Under-limit message rejected: {resp.text}"


@pytest.mark.stress
@pytest.mark.asyncio
async def test_many_recipients_200(transport, base_url):
    """Register 200 users, send messages to all from one sender concurrently."""
    count = 200
    sender = _generate_user_credentials()
    recipients = [_generate_user_credentials() for _ in range(count)]

    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        await client.post("/api/v1/keys/register", json=_make_register_payload(sender))

        # Register all recipients concurrently
        reg_tasks = [
            client.post("/api/v1/keys/register", json=_make_register_payload(r))
            for r in recipients
        ]
        reg_responses = await asyncio.gather(*reg_tasks)
        assert all(r.status_code == 201 for r in reg_responses)

        # Send one message to each recipient concurrently
        t0 = time.perf_counter()
        send_tasks = [
            client.post("/api/v1/messages/send", json=_make_send_payload(sender, r["user_id"]))
            for r in recipients
        ]
        send_responses = await asyncio.gather(*send_tasks)
        elapsed = time.perf_counter() - t0

        assert all(r.status_code == 201 for r in send_responses)

        # Verify isolation: each recipient got exactly 1 message
        for r in recipients[:10]:  # spot-check first 10
            resp = await client.post("/api/v1/messages/pull", json={
                "user_id": r["user_id"], "acked_seq": 0, "limit": 100,
            })
            assert len(resp.json()["messages"]) == 1

    print(f"\n  [PERF] Broadcast to {count} recipients: {elapsed:.3f}s ({count/elapsed:.0f} msg/s)")


@pytest.mark.stress
@pytest.mark.asyncio
async def test_concurrent_pull_50(transport, base_url):
    """50 concurrent pull requests for the same user with 500 queued messages."""
    sender = _generate_user_credentials()
    recipient = _generate_user_credentials()

    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        await client.post("/api/v1/keys/register", json=_make_register_payload(sender))
        await client.post("/api/v1/keys/register", json=_make_register_payload(recipient))

        # Queue 500 messages
        tasks = [
            client.post("/api/v1/messages/send", json=_make_send_payload(sender, recipient["user_id"]))
            for _ in range(500)
        ]
        await asyncio.gather(*tasks)

        # 50 concurrent pulls
        pull_payload = {"user_id": recipient["user_id"], "acked_seq": 0, "limit": 500}

        t0 = time.perf_counter()
        pull_tasks = [client.post("/api/v1/messages/pull", json=pull_payload) for _ in range(50)]
        pull_responses = await asyncio.gather(*pull_tasks)
        elapsed = time.perf_counter() - t0

        for resp in pull_responses:
            assert resp.status_code == 200
            assert len(resp.json()["messages"]) == 500

    print(f"\n  [PERF] 50 concurrent pulls (500 msgs each): {elapsed:.3f}s ({50/elapsed:.0f} pulls/s)")


@pytest.mark.stress
@pytest.mark.asyncio
async def test_message_ttl_expiry(transport, base_url):
    """Send messages, wait for TTL to expire, verify cleanup removes them."""
    from server.services.key_service import key_service

    # Reset global services to ensure test isolation
    message_service.reset()
    key_service.reset()

    original_ttl = config.MESSAGE_TTL
    try:
        object.__setattr__(config, "MESSAGE_TTL", 1)

        sender = _generate_user_credentials()
        recipient = _generate_user_credentials()

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            await client.post("/api/v1/keys/register", json=_make_register_payload(sender))
            await client.post("/api/v1/keys/register", json=_make_register_payload(recipient))

            # Send 10 messages
            for _ in range(10):
                resp = await client.post(
                    "/api/v1/messages/send",
                    json=_make_send_payload(sender, recipient["user_id"]),
                )
                assert resp.status_code == 201

            # Verify messages exist
            resp = await client.post("/api/v1/messages/pull", json={
                "user_id": recipient["user_id"], "acked_seq": 0, "limit": 100,
            })
            assert len(resp.json()["messages"]) == 10

            # Wait for TTL to expire
            await asyncio.sleep(1.5)

            # Run cleanup
            removed = await message_service.cleanup_expired_messages()
            assert removed == 10

            # Verify messages are gone
            resp = await client.post("/api/v1/messages/pull", json={
                "user_id": recipient["user_id"], "acked_seq": 0, "limit": 100,
            })
            assert len(resp.json()["messages"]) == 0
    finally:
        object.__setattr__(config, "MESSAGE_TTL", original_ttl)


@pytest.mark.stress
@pytest.mark.asyncio
async def test_queue_ordering_1000(transport, base_url):
    """Send 1000 messages sequentially, pull in batches of 100, verify strict ordering."""
    count = 1000
    sender = _generate_user_credentials()
    recipient = _generate_user_credentials()

    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        await client.post("/api/v1/keys/register", json=_make_register_payload(sender))
        await client.post("/api/v1/keys/register", json=_make_register_payload(recipient))

        # Send sequentially to guarantee ordering
        for _ in range(count):
            resp = await client.post(
                "/api/v1/messages/send",
                json=_make_send_payload(sender, recipient["user_id"]),
            )
            assert resp.status_code == 201

        # Pull in batches of 100
        all_messages = []
        acked_seq = 0
        batch_count = 0
        while True:
            resp = await client.post("/api/v1/messages/pull", json={
                "user_id": recipient["user_id"],
                "acked_seq": acked_seq,
                "limit": 100,
            })
            data = resp.json()
            batch = data["messages"]
            if not batch:
                break
            all_messages.extend(batch)
            acked_seq = data["last_seq"]
            batch_count += 1
            if not data["has_more"]:
                break

        assert len(all_messages) == count
        assert batch_count == 10

        # Verify strict ordering
        seqs = [m["server_seq"] for m in all_messages]
        assert seqs == list(range(1, count + 1)), "Messages not in expected server_seq order"


@pytest.mark.stress
@pytest.mark.asyncio
async def test_mixed_workload_simulation(transport, base_url):
    """Simulate realistic mixed workload: 100 users, each sending 50 messages to random others."""
    import random

    user_count = 100
    msgs_per_user = 50
    users = [_generate_user_credentials() for _ in range(user_count)]

    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        # Register all users
        reg_tasks = [client.post("/api/v1/keys/register", json=_make_register_payload(u)) for u in users]
        reg_responses = await asyncio.gather(*reg_tasks)
        assert all(r.status_code == 201 for r in reg_responses)

        # Each user sends msgs_per_user messages to random recipients
        t0 = time.perf_counter()
        all_send_tasks = []
        for sender in users:
            for _ in range(msgs_per_user):
                recipient = random.choice(users)
                while recipient["user_id"] == sender["user_id"]:
                    recipient = random.choice(users)
                all_send_tasks.append(
                    client.post("/api/v1/messages/send", json=_make_send_payload(sender, recipient["user_id"]))
                )

        # Send in batches of 1000
        total_sent = 0
        batch_size = 1000
        for i in range(0, len(all_send_tasks), batch_size):
            batch = all_send_tasks[i:i+batch_size]
            responses = await asyncio.gather(*batch)
            total_sent += sum(1 for r in responses if r.status_code == 201)
        send_elapsed = time.perf_counter() - t0

        total_msgs = user_count * msgs_per_user
        assert total_sent == total_msgs, f"Only {total_sent}/{total_msgs} sends succeeded"

        # Pull for a sample of users and verify they have messages
        t1 = time.perf_counter()
        pull_tasks = [
            client.post("/api/v1/messages/pull", json={
                "user_id": u["user_id"], "acked_seq": 0, "limit": 1000,
            })
            for u in users
        ]
        pull_responses = await asyncio.gather(*pull_tasks)
        pull_elapsed = time.perf_counter() - t1

        total_pulled = sum(len(r.json()["messages"]) for r in pull_responses)
        assert total_pulled == total_msgs  # All messages accounted for

    print(f"\n  [PERF] Mixed workload: {user_count} users × {msgs_per_user} msgs = {total_msgs} total")
    print(f"  [PERF] Send: {send_elapsed:.3f}s ({total_msgs/send_elapsed:.0f} msg/s)")
    print(f"  [PERF] Pull all: {pull_elapsed:.3f}s ({total_pulled/pull_elapsed:.0f} msg/s)")
