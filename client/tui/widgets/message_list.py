"""Message list widget for displaying chat messages."""
from typing import List, Optional, Tuple

from textual.reactive import reactive
from textual.widgets import Static
from textual.message import Message as TextualMessage

from client.services.chat_service import ChatService
from client.storage.models import Contact, Message, MessageDirection, MessageStatus
from client.utils.logger import get_logger

logger = get_logger(__name__)


class MessageListWidget(Static):
    """Widget for displaying messages with decryption support."""

    DEFAULT_CSS = """
    MessageListWidget {
        height: 1fr;
        overflow-y: scroll;
        padding: 1;
    }

    .message-sent {
        text-align: right;
        color: $success;
        margin: 1 0;
    }

    .message-received {
        text-align: left;
        color: $primary;
        margin: 1 0;
    }

    .message-pending {
        color: $warning;
    }

    .message-failed {
        color: $error;
    }

    .message-queued {
        color: $success;
    }

    .timestamp {
        color: $text-muted;
    }

    .empty-state {
        text-align: center;
        color: $text-muted;
        padding: 2;
    }
    """

    messages: reactive[List[Tuple[Message, str]]] = reactive(list)

    def __init__(
        self,
        chat_service: ChatService,
        current_contact: Optional[Contact] = None,
        **kwargs
    ) -> None:
        """Initialize the message list widget."""
        super().__init__(**kwargs)
        self.chat_service = chat_service
        self._current_contact = current_contact
        self._decryption_cache: dict[str, str] = {}
        self._messages_list: List[Tuple[Message, str]] = []

    @property
    def current_contact(self) -> Optional[Contact]:
        """Get the current contact."""
        return self._current_contact

    @current_contact.setter
    def current_contact(self, contact: Optional[Contact]) -> None:
        """Set the current contact."""
        self._current_contact = contact
        self._decryption_cache.clear()

    async def load_messages(self, contact: Contact, limit: int = 100) -> None:
        """Load and decrypt messages for a contact."""
        self._current_contact = contact
        self._decryption_cache.clear()

        encrypted_messages = self.chat_service.get_messages(contact, limit)

        decrypted = []
        for msg in encrypted_messages:
            plaintext = await self._decrypt_message(msg, contact)
            decrypted.append((msg, plaintext))

        self._messages_list = decrypted
        self._render_messages()

        logger.debug(f"Loaded {len(decrypted)} messages for {contact.alias}")

    async def add_message(self, message: Message, plaintext: str) -> None:
        """Add a new message to the list."""
        self._messages_list.append((message, plaintext))
        self._decryption_cache[message.message_id] = plaintext
        self._render_messages()
        self.call_after_refresh(self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the message list."""
        self.scroll_end(animate=False)

    def _render_messages(self) -> None:
        """Render messages to the widget."""
        if not self._messages_list:
            self.update(
                '[class="empty-state"]No messages yet.\nStart the conversation![/class]'
            )
            return

        lines = []
        for msg, plaintext in self._messages_list:
            timestamp = msg.timestamp.strftime("%H:%M")

            if msg.direction == MessageDirection.SENT:
                prefix = ">"
            else:
                prefix = "<"

            if msg.direction == MessageDirection.SENT:
                status_text = {
                    MessageStatus.PENDING: "[...] ",
                    MessageStatus.QUEUED: "[Q] ",
                    MessageStatus.FAILED: "[ERR] ",
                }.get(msg.status, "")
            else:
                status_text = ""

            line = f"[dim]{timestamp}[/] {prefix} {plaintext} {status_text}"
            lines.append(line)

        self.update("\n".join(lines))

    async def _decrypt_message(self, message: Message, sender: Contact) -> str:
        """Decrypt a message with caching."""
        if message.message_id in self._decryption_cache:
            return self._decryption_cache[message.message_id]

        plaintext = await self.chat_service.decrypt_message(message, sender)
        self._decryption_cache[message.message_id] = plaintext

        return plaintext

    def clear_messages(self) -> None:
        """Clear all messages."""
        self._messages_list = []
        self._decryption_cache.clear()
        self.update('[class="empty-state"]No messages yet.[/class]')
