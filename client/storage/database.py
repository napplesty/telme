"""Database management module using SQLite."""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from client.storage.models import (
    Contact,
    Message,
    MessageDirection,
    MessageStatus,
    SyncState,
)
from client.utils.logger import get_logger

logger = get_logger(__name__)


sqlite3.register_adapter(datetime, lambda value: value.isoformat())
sqlite3.register_converter(
    "TIMESTAMP", lambda value: datetime.fromisoformat(value.decode("utf-8"))
)


class Database:
    """SQLite database manager for client storage."""

    def __init__(self, db_path: Path):
        """Initialize database.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[sqlite3.Connection] = None
        self._initialize_database()

    @property
    def connection(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def _initialize_database(self) -> None:
        """Initialize database schema for the current application version."""
        logger.info(f"Initializing database at {self.db_path}")

        with self.connection as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT UNIQUE NOT NULL,
                    public_key TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT UNIQUE NOT NULL,
                    sender_id TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    encrypted_message TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    server_seq INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_state (
                    user_id TEXT PRIMARY KEY,
                    acked_seq INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_server_seq ON messages(server_seq)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_contacts_user_id ON contacts(user_id)"
            )

            conn.commit()
            logger.info("Database initialized successfully")

    def add_contact(self, user_id: str, public_key: str, alias: str) -> Contact:
        """Add a new contact."""
        with self.connection as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO contacts (user_id, public_key, alias)
                VALUES (?, ?, ?)
                """,
                (user_id, public_key, alias),
            )
            contact_id = cursor.lastrowid
            conn.commit()

        logger.info(f"Added contact: {alias} ({user_id[:8]}...)")

        return Contact(
            id=contact_id,
            user_id=user_id,
            public_key=public_key,
            alias=alias,
            created_at=datetime.now(),
        )

    def get_contact(self, user_id: str) -> Optional[Contact]:
        """Get contact by user ID."""
        with self.connection as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contacts WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

        if row:
            return Contact.from_dict(dict(row))
        return None

    def get_contact_by_alias(self, alias: str) -> Optional[Contact]:
        """Get contact by alias."""
        with self.connection as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contacts WHERE alias = ?", (alias,))
            row = cursor.fetchone()

        if row:
            return Contact.from_dict(dict(row))
        return None

    def get_all_contacts(self) -> List[Contact]:
        """Get all contacts."""
        with self.connection as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contacts ORDER BY alias")
            rows = cursor.fetchall()

        return [Contact.from_dict(dict(row)) for row in rows]

    def update_contact_alias(self, user_id: str, new_alias: str) -> bool:
        """Update contact alias."""
        with self.connection as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE contacts SET alias = ? WHERE user_id = ?",
                (new_alias, user_id),
            )
            updated = cursor.rowcount > 0
            conn.commit()

        if updated:
            logger.info(f"Updated contact alias: {user_id[:8]}... -> {new_alias}")

        return updated

    def delete_contact(self, user_id: str) -> bool:
        """Delete a contact."""
        with self.connection as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM contacts WHERE user_id = ?", (user_id,))
            deleted = cursor.rowcount > 0
            conn.commit()

        if deleted:
            logger.info(f"Deleted contact: {user_id[:8]}...")

        return deleted

    def add_message(
        self,
        message_id: str,
        sender_id: str,
        recipient_id: str,
        encrypted_message: str,
        nonce: str,
        signature: str,
        direction: MessageDirection,
        status: MessageStatus,
        timestamp: datetime,
        server_seq: Optional[int] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Message:
        """Add a new message."""
        owns_connection = conn is None
        active_conn = conn or self.connection
        cursor = active_conn.cursor()

        cursor.execute(
            """
            INSERT INTO messages (
                message_id, sender_id, recipient_id, encrypted_message,
                nonce, signature, direction, status, timestamp, server_seq
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                sender_id,
                recipient_id,
                encrypted_message,
                nonce,
                signature,
                direction.value,
                status.value,
                timestamp,
                server_seq,
            ),
        )

        if owns_connection:
            active_conn.commit()

        msg_id = cursor.lastrowid
        logger.debug(f"Added message: {message_id}")

        return Message(
            id=msg_id,
            message_id=message_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            encrypted_message=encrypted_message,
            nonce=nonce,
            signature=signature,
            direction=direction,
            status=status,
            timestamp=timestamp,
            server_seq=server_seq,
            created_at=datetime.now(),
        )

    def get_message(self, message_id: str) -> Optional[Message]:
        """Get message by message ID."""
        with self.connection as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM messages WHERE message_id = ?", (message_id,))
            row = cursor.fetchone()

        if row:
            return Message.from_dict(dict(row))
        return None

    def get_messages_by_contact(
        self,
        user_id: str,
        limit: int = 100,
        before_timestamp: Optional[datetime] = None,
    ) -> List[Message]:
        """Get messages with a specific contact."""
        query = """
            SELECT * FROM messages
            WHERE (sender_id = ? OR recipient_id = ?)
        """
        params = [user_id, user_id]

        if before_timestamp:
            query += " AND timestamp < ?"
            params.append(before_timestamp)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self.connection as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        messages = [Message.from_dict(dict(row)) for row in rows]
        return list(reversed(messages))

    def update_message_status(self, message_id: str, status: MessageStatus) -> bool:
        """Update message status."""
        with self.connection as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE messages SET status = ? WHERE message_id = ?",
                (status.value, message_id),
            )
            updated = cursor.rowcount > 0
            conn.commit()

        if updated:
            logger.debug(f"Updated message status: {message_id} -> {status.value}")

        return updated

    def get_last_message_timestamp(self, user_id: str) -> Optional[datetime]:
        """Get timestamp of last message with a contact."""
        with self.connection as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MAX(timestamp) as last_timestamp FROM messages
                WHERE sender_id = ? OR recipient_id = ?
                """,
                (user_id, user_id),
            )
            row = cursor.fetchone()

        if row and row["last_timestamp"]:
            return datetime.fromisoformat(row["last_timestamp"])
        return None

    def get_sync_state(self, user_id: str) -> SyncState:
        """Get persisted synchronization state for a user."""
        with self.connection as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sync_state WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

        if row:
            return SyncState.from_dict(dict(row))

        return SyncState(
            user_id=user_id,
            acked_seq=0,
            updated_at=datetime.now(),
        )

    def update_sync_state(
        self,
        user_id: str,
        acked_seq: int,
        conn: Optional[sqlite3.Connection] = None,
    ) -> SyncState:
        """Persist synchronization state for a user."""
        owns_connection = conn is None
        active_conn = conn or self.connection
        cursor = active_conn.cursor()
        updated_at = datetime.now()
        cursor.execute(
            """
            INSERT INTO sync_state (user_id, acked_seq, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                acked_seq = excluded.acked_seq,
                updated_at = excluded.updated_at
            """,
            (user_id, acked_seq, updated_at),
        )

        if owns_connection:
            active_conn.commit()

        return SyncState(
            user_id=user_id,
            acked_seq=acked_seq,
            updated_at=updated_at,
        )

    def persist_received_batch(
        self,
        user_id: str,
        messages_data: Sequence[dict],
        acked_seq: int,
    ) -> tuple[list[Message], SyncState]:
        """Persist a batch of received messages and update sync state atomically."""
        persisted_messages: list[Message] = []

        with self.connection as conn:
            for msg_data in messages_data:
                persisted_messages.append(
                    self.add_message(
                        message_id=msg_data["message_id"],
                        sender_id=msg_data["sender_id"],
                        recipient_id=msg_data["recipient_id"],
                        encrypted_message=msg_data["encrypted_message"],
                        nonce=msg_data["nonce"],
                        signature=msg_data["signature"],
                        direction=MessageDirection.RECEIVED,
                        status=MessageStatus.QUEUED,
                        timestamp=datetime.fromisoformat(msg_data["timestamp"]),
                        server_seq=msg_data["server_seq"],
                        conn=conn,
                    )
                )

            sync_state = self.update_sync_state(
                user_id=user_id,
                acked_seq=acked_seq,
                conn=conn,
            )
            conn.commit()

        if persisted_messages:
            logger.debug(
                f"Persisted {len(persisted_messages)} received messages for {user_id[:8]}..."
            )

        return persisted_messages, sync_state

    def delete_messages(self, user_id: str) -> int:
        """Delete all messages with a contact."""
        with self.connection as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM messages WHERE sender_id = ? OR recipient_id = ?",
                (user_id, user_id),
            )
            deleted = cursor.rowcount
            conn.commit()

        if deleted > 0:
            logger.info(f"Deleted {deleted} messages with contact {user_id[:8]}...")

        return deleted

    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("Database connection closed")
