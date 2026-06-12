"""Locust load testing file for Telme server.

Usage:
    locust -f tests/locustfile.py --host http://localhost:8000

This file is for manual load testing against a live server instance.
It is NOT run by pytest.
"""
import base64
import hashlib
import os
import random
import threading
from datetime import datetime

from locust import HttpUser, between, task
from nacl.signing import SigningKey


# Thread-safe shared list of registered user_ids
_registered_users_lock = threading.Lock()
_registered_users: list[str] = []


class TelmeUser(HttpUser):
    """Simulates a Telme chat user performing registration, sending, and pulling."""

    wait_time = between(0.5, 2.0)

    def on_start(self):
        """Register a new user with valid Ed25519 credentials on start."""
        self.signing_key = SigningKey.generate()
        self.verify_key = self.signing_key.verify_key
        self.pubkey_bytes = bytes(self.verify_key)
        self.pubkey_b64 = base64.b64encode(self.pubkey_bytes).decode()
        self.user_id = hashlib.sha256(self.pubkey_bytes).hexdigest()

        # Create valid signature (signing the public key itself)
        signature = self.signing_key.sign(self.pubkey_bytes).signature
        signature_b64 = base64.b64encode(signature).decode()

        payload = {
            "public_key": self.pubkey_b64,
            "signature": signature_b64,
            "timestamp": datetime.now().isoformat(),
        }

        with self.client.post(
            "/api/v1/keys/register",
            json=payload,
            name="/api/v1/keys/register",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                response.success()
                # Add to shared user list for cross-user messaging
                with _registered_users_lock:
                    _registered_users.append(self.user_id)
            else:
                response.failure(f"Registration failed: {response.status_code} {response.text}")

    @task(3)
    def send_message(self):
        """Send a message to a random registered user."""
        with _registered_users_lock:
            if len(_registered_users) < 2:
                return
            # Pick a random recipient that is not self
            candidates = [uid for uid in _registered_users if uid != self.user_id]
            if not candidates:
                return
            recipient_id = random.choice(candidates)

        # Generate random encrypted message payload
        encrypted_message = base64.b64encode(os.urandom(128)).decode()
        nonce = base64.b64encode(os.urandom(24)).decode()
        signature = base64.b64encode(os.urandom(64)).decode()

        payload = {
            "sender_id": self.user_id,
            "recipient_id": recipient_id,
            "encrypted_message": encrypted_message,
            "nonce": nonce,
            "signature": signature,
            "timestamp": datetime.now().isoformat(),
        }

        with self.client.post(
            "/api/v1/messages/send",
            json=payload,
            name="/api/v1/messages/send",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                response.success()
            elif response.status_code == 404:
                # Recipient may not be registered yet on this server instance
                response.success()
            else:
                response.failure(f"Send failed: {response.status_code} {response.text}")

    @task(1)
    def pull_messages(self):
        """Pull messages for the current user."""
        payload = {
            "user_id": self.user_id,
            "acked_seq": 0,
            "limit": 100,
        }

        with self.client.post(
            "/api/v1/messages/pull",
            json=payload,
            name="/api/v1/messages/pull",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Pull failed: {response.status_code} {response.text}")
