"""Functional tests for client SQLite database."""
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from client.storage.database import Database
from client.storage.models import (
    Contact,
    Message,
    MessageDirection,
    MessageStatus,
    SyncState,
)


@pytest.fixture
def db(tmp_path: Path) -> Database:
    """Create a fresh Database instance using a temporary path."""
    db_path = tmp_path / "test.db"
    database = Database(db_path)
    yield database
    database.close()


# ---------------------------------------------------------------------------
# Database initialization
# ---------------------------------------------------------------------------


class TestDatabaseInit:
    """Tests for database schema initialization."""

    def test_tables_created(self, db: Database):
        """Initializing the DB should create contacts, messages, and sync_state tables."""
        cursor = db.connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row["name"] for row in cursor.fetchall()}
        assert "contacts" in tables
        assert "messages" in tables
        assert "sync_state" in tables

    def test_indexes_created(self, db: Database):
        """Initializing the DB should create expected indexes."""
        cursor = db.connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        indexes = {row["name"] for row in cursor.fetchall()}
        assert "idx_messages_sender" in indexes
        assert "idx_messages_recipient" in indexes
        assert "idx_messages_timestamp" in indexes
        assert "idx_messages_server_seq" in indexes
        assert "idx_contacts_user_id" in indexes

    def test_idempotent_initialization(self, tmp_path: Path):
        """Creating a Database twice on the same file should not fail."""
        db_path = tmp_path / "test.db"
        db1 = Database(db_path)
        db1.close()
        db2 = Database(db_path)
        db2.close()


# ---------------------------------------------------------------------------
# Contact CRUD
# ---------------------------------------------------------------------------


class TestContactCRUD:
    """Tests for contact add/get/get_all/update_alias/delete."""

    def test_add_contact(self, db: Database):
        """add_contact should return a Contact with a valid id."""
        contact = db.add_contact(
            user_id="a" * 64,
            public_key="cHVia2V5YmFzZTY0",
            alias="Alice",
        )
        assert isinstance(contact, Contact)
        assert contact.id is not None
        assert contact.user_id == "a" * 64
        assert contact.alias == "Alice"

    def test_get_contact(self, db: Database):
        """get_contact should retrieve the stored contact."""
        user_id = "b" * 64
        db.add_contact(user_id=user_id, public_key="key123", alias="Bob")

        contact = db.get_contact(user_id)
        assert contact is not None
        assert contact.user_id == user_id
        assert contact.alias == "Bob"
        assert contact.public_key == "key123"

    def test_get_contact_returns_none_for_missing(self, db: Database):
        """get_contact for non-existent user_id should return None."""
        assert db.get_contact("z" * 64) is None

    def test_get_all_contacts(self, db: Database):
        """get_all_contacts should return all stored contacts ordered by alias."""
        db.add_contact(user_id="c" * 64, public_key="k1", alias="Charlie")
        db.add_contact(user_id="a" * 64, public_key="k2", alias="Alice")
        db.add_contact(user_id="b" * 64, public_key="k3", alias="Bob")

        contacts = db.get_all_contacts()
        assert len(contacts) == 3
        aliases = [c.alias for c in contacts]
        assert aliases == ["Alice", "Bob", "Charlie"]

    def test_update_contact_alias(self, db: Database):
        """update_contact_alias should change the alias."""
        user_id = "d" * 64
        db.add_contact(user_id=user_id, public_key="k1", alias="OldName")

        result = db.update_contact_alias(user_id, "NewName")
        assert result is True

        contact = db.get_contact(user_id)
        assert contact.alias == "NewName"

    def test_update_contact_alias_nonexistent(self, db: Database):
        """update_contact_alias for missing user should return False."""
        result = db.update_contact_alias("x" * 64, "Ghost")
        assert result is False

    def test_delete_contact(self, db: Database):
        """delete_contact should remove the contact."""
        user_id = "e" * 64
        db.add_contact(user_id=user_id, public_key="k1", alias="Eve")

        result = db.delete_contact(user_id)
        assert result is True
        assert db.get_contact(user_id) is None

    def test_delete_contact_nonexistent(self, db: Database):
        """delete_contact for missing user should return False."""
        result = db.delete_contact("y" * 64)
        assert result is False

    def test_duplicate_contact_user_id_raises(self, db: Database):
        """Adding a contact with duplicate user_id should raise IntegrityError."""
        user_id = "f" * 64
        db.add_contact(user_id=user_id, public_key="k1", alias="First")

        with pytest.raises(sqlite3.IntegrityError):
            db.add_contact(user_id=user_id, public_key="k2", alias="Second")


# ---------------------------------------------------------------------------
# Message CRUD
# ---------------------------------------------------------------------------


class TestMessageCRUD:
    """Tests for message add/get/get_by_contact with pagination."""

    def _make_message_id(self):
        return str(uuid4())

    def test_add_message(self, db: Database):
        """add_message should return a Message with a valid id."""
        msg = db.add_message(
            message_id=self._make_message_id(),
            sender_id="a" * 64,
            recipient_id="b" * 64,
            encrypted_message="Y2lwaGVydGV4dA==",
            nonce="bm9uY2U=",
            signature="c2lnbmF0dXJl",
            direction=MessageDirection.SENT,
            status=MessageStatus.QUEUED,
            timestamp=datetime.now(),
            server_seq=1,
        )
        assert isinstance(msg, Message)
        assert msg.id is not None
        assert msg.direction == MessageDirection.SENT
        assert msg.status == MessageStatus.QUEUED

    def test_get_message(self, db: Database):
        """get_message should retrieve message by message_id."""
        msg_id = self._make_message_id()
        db.add_message(
            message_id=msg_id,
            sender_id="a" * 64,
            recipient_id="b" * 64,
            encrypted_message="ct",
            nonce="nc",
            signature="sig",
            direction=MessageDirection.RECEIVED,
            status=MessageStatus.QUEUED,
            timestamp=datetime.now(),
            server_seq=5,
        )

        retrieved = db.get_message(msg_id)
        assert retrieved is not None
        assert retrieved.message_id == msg_id
        assert retrieved.server_seq == 5
        assert retrieved.direction == MessageDirection.RECEIVED

    def test_get_message_returns_none_for_missing(self, db: Database):
        """get_message for non-existent message_id should return None."""
        assert db.get_message("nonexistent-id") is None

    def test_get_messages_by_contact(self, db: Database):
        """get_messages_by_contact should return messages involving a contact."""
        contact_id = "a" * 64
        my_id = "b" * 64

        # Add sent message
        db.add_message(
            message_id=self._make_message_id(),
            sender_id=my_id,
            recipient_id=contact_id,
            encrypted_message="ct1",
            nonce="nc1",
            signature="sig1",
            direction=MessageDirection.SENT,
            status=MessageStatus.QUEUED,
            timestamp=datetime(2024, 1, 1, 10, 0, 0),
            server_seq=1,
        )
        # Add received message
        db.add_message(
            message_id=self._make_message_id(),
            sender_id=contact_id,
            recipient_id=my_id,
            encrypted_message="ct2",
            nonce="nc2",
            signature="sig2",
            direction=MessageDirection.RECEIVED,
            status=MessageStatus.QUEUED,
            timestamp=datetime(2024, 1, 1, 10, 1, 0),
            server_seq=2,
        )

        messages = db.get_messages_by_contact(contact_id, limit=100)
        assert len(messages) == 2
        # Should be in chronological order (reversed from DESC)
        assert messages[0].timestamp < messages[1].timestamp

    def test_get_messages_by_contact_with_limit(self, db: Database):
        """get_messages_by_contact should respect the limit parameter."""
        contact_id = "c" * 64

        for i in range(5):
            db.add_message(
                message_id=self._make_message_id(),
                sender_id=contact_id,
                recipient_id="d" * 64,
                encrypted_message=f"ct{i}",
                nonce=f"nc{i}",
                signature=f"sig{i}",
                direction=MessageDirection.RECEIVED,
                status=MessageStatus.QUEUED,
                timestamp=datetime(2024, 1, 1, 10, i, 0),
                server_seq=i + 1,
            )

        messages = db.get_messages_by_contact(contact_id, limit=3)
        assert len(messages) == 3

    def test_get_messages_by_contact_before_timestamp(self, db: Database):
        """get_messages_by_contact with before_timestamp should filter correctly."""
        contact_id = "e" * 64

        db.add_message(
            message_id=self._make_message_id(),
            sender_id=contact_id,
            recipient_id="f" * 64,
            encrypted_message="ct1",
            nonce="nc1",
            signature="sig1",
            direction=MessageDirection.RECEIVED,
            status=MessageStatus.QUEUED,
            timestamp=datetime(2024, 1, 1, 9, 0, 0),
            server_seq=1,
        )
        db.add_message(
            message_id=self._make_message_id(),
            sender_id=contact_id,
            recipient_id="f" * 64,
            encrypted_message="ct2",
            nonce="nc2",
            signature="sig2",
            direction=MessageDirection.RECEIVED,
            status=MessageStatus.QUEUED,
            timestamp=datetime(2024, 1, 1, 11, 0, 0),
            server_seq=2,
        )

        messages = db.get_messages_by_contact(
            contact_id, limit=100, before_timestamp=datetime(2024, 1, 1, 10, 0, 0)
        )
        assert len(messages) == 1
        assert messages[0].server_seq == 1

    def test_duplicate_message_id_raises(self, db: Database):
        """Adding a message with duplicate message_id should raise IntegrityError."""
        msg_id = self._make_message_id()
        db.add_message(
            message_id=msg_id,
            sender_id="a" * 64,
            recipient_id="b" * 64,
            encrypted_message="ct",
            nonce="nc",
            signature="sig",
            direction=MessageDirection.SENT,
            status=MessageStatus.QUEUED,
            timestamp=datetime.now(),
            server_seq=1,
        )

        with pytest.raises(sqlite3.IntegrityError):
            db.add_message(
                message_id=msg_id,
                sender_id="a" * 64,
                recipient_id="b" * 64,
                encrypted_message="ct2",
                nonce="nc2",
                signature="sig2",
                direction=MessageDirection.SENT,
                status=MessageStatus.QUEUED,
                timestamp=datetime.now(),
                server_seq=2,
            )


# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------


class TestSyncState:
    """Tests for sync state get/update/persistence."""

    def test_get_sync_state_default(self, db: Database):
        """get_sync_state for unknown user should return default (acked_seq=0)."""
        state = db.get_sync_state("g" * 64)
        assert isinstance(state, SyncState)
        assert state.acked_seq == 0
        assert state.user_id == "g" * 64

    def test_update_sync_state(self, db: Database):
        """update_sync_state should persist the new acked_seq."""
        user_id = "h" * 64
        state = db.update_sync_state(user_id, acked_seq=42)
        assert state.acked_seq == 42
        assert state.user_id == user_id

    def test_sync_state_persistence(self, db: Database):
        """After updating, get_sync_state should return the updated value."""
        user_id = "i" * 64
        db.update_sync_state(user_id, acked_seq=10)

        retrieved = db.get_sync_state(user_id)
        assert retrieved.acked_seq == 10

    def test_sync_state_upsert(self, db: Database):
        """update_sync_state called twice should update (not duplicate)."""
        user_id = "j" * 64
        db.update_sync_state(user_id, acked_seq=5)
        db.update_sync_state(user_id, acked_seq=15)

        state = db.get_sync_state(user_id)
        assert state.acked_seq == 15


# ---------------------------------------------------------------------------
# Batch persist
# ---------------------------------------------------------------------------


class TestBatchPersist:
    """Tests for persist_received_batch atomicity."""

    def test_persist_received_batch(self, db: Database):
        """persist_received_batch should store messages and update sync state."""
        user_id = "k" * 64
        messages_data = [
            {
                "message_id": str(uuid4()),
                "sender_id": "l" * 64,
                "recipient_id": user_id,
                "encrypted_message": "ct1",
                "nonce": "nc1",
                "signature": "sig1",
                "timestamp": datetime(2024, 1, 1, 12, 0, 0).isoformat(),
                "server_seq": 1,
            },
            {
                "message_id": str(uuid4()),
                "sender_id": "l" * 64,
                "recipient_id": user_id,
                "encrypted_message": "ct2",
                "nonce": "nc2",
                "signature": "sig2",
                "timestamp": datetime(2024, 1, 1, 12, 1, 0).isoformat(),
                "server_seq": 2,
            },
        ]

        persisted_msgs, sync_state = db.persist_received_batch(
            user_id=user_id,
            messages_data=messages_data,
            acked_seq=2,
        )

        assert len(persisted_msgs) == 2
        assert all(isinstance(m, Message) for m in persisted_msgs)
        assert all(m.direction == MessageDirection.RECEIVED for m in persisted_msgs)
        assert all(m.status == MessageStatus.QUEUED for m in persisted_msgs)
        assert sync_state.acked_seq == 2

    def test_persist_received_batch_updates_sync_state(self, db: Database):
        """After persist_received_batch, get_sync_state should reflect new acked_seq."""
        user_id = "m" * 64
        messages_data = [
            {
                "message_id": str(uuid4()),
                "sender_id": "n" * 64,
                "recipient_id": user_id,
                "encrypted_message": "ct",
                "nonce": "nc",
                "signature": "sig",
                "timestamp": datetime.now().isoformat(),
                "server_seq": 7,
            },
        ]

        db.persist_received_batch(
            user_id=user_id,
            messages_data=messages_data,
            acked_seq=7,
        )

        state = db.get_sync_state(user_id)
        assert state.acked_seq == 7

    def test_persist_received_batch_empty(self, db: Database):
        """persist_received_batch with empty list should just update sync state."""
        user_id = "o" * 64
        persisted_msgs, sync_state = db.persist_received_batch(
            user_id=user_id,
            messages_data=[],
            acked_seq=0,
        )
        assert persisted_msgs == []
        assert sync_state.acked_seq == 0

    def test_persist_received_batch_duplicate_message_id_raises(self, db: Database):
        """persist_received_batch with duplicate message_id should raise IntegrityError."""
        user_id = "p" * 64
        msg_id = str(uuid4())
        messages_data = [
            {
                "message_id": msg_id,
                "sender_id": "q" * 64,
                "recipient_id": user_id,
                "encrypted_message": "ct",
                "nonce": "nc",
                "signature": "sig",
                "timestamp": datetime.now().isoformat(),
                "server_seq": 1,
            },
        ]

        # First batch succeeds
        db.persist_received_batch(
            user_id=user_id,
            messages_data=messages_data,
            acked_seq=1,
        )

        # Second batch with same message_id should fail
        with pytest.raises(sqlite3.IntegrityError):
            db.persist_received_batch(
                user_id=user_id,
                messages_data=messages_data,
                acked_seq=2,
            )
