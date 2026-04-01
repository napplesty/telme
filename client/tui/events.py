"""Custom events for TUI components."""
from textual.message import Message

from client.storage.models import Contact
from client.storage.models import Message as StorageMessage


class ContactSelected(Message):
    """Event fired when a contact is selected."""

    def __init__(self, contact: Contact) -> None:
        """Initialize event.

        Args:
            contact: The selected contact.
        """
        self.contact = contact
        super().__init__()


class MessageReceived(Message):
    """Event fired when a new message is received."""

    def __init__(self, message: StorageMessage, plaintext: str) -> None:
        """Initialize event.

        Args:
            message: The received message.
            plaintext: The decrypted message content.
        """
        self.message = message
        self.plaintext = plaintext
        super().__init__()


class MessageSent(Message):
    """Event fired when a message is sent."""

    def __init__(self, message: StorageMessage, plaintext: str) -> None:
        """Initialize event.

        Args:
            message: The sent message.
            plaintext: The message content.
        """
        self.message = message
        self.plaintext = plaintext
        super().__init__()


class ContactAdded(Message):
    """Event fired when a new contact is added."""

    def __init__(self, contact: Contact) -> None:
        """Initialize event.

        Args:
            contact: The added contact.
        """
        self.contact = contact
        super().__init__()


class StatusChanged(Message):
    """Event fired when connection or user status changes."""

    def __init__(self, status: str, details: str = "") -> None:
        """Initialize event.

        Args:
            status: The new status (e.g., 'connected', 'disconnected', 'error').
            details: Additional details about the status change.
        """
        self.status = status
        self.details = details
        super().__init__()
