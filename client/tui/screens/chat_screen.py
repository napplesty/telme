"""Main chat screen containing the chat interface."""
import asyncio
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Input

from client.services.chat_service import ChatService
from client.services.contact_service import ContactService
from client.storage.models import Contact, Message, MessageStatus
from client.tui.widgets.contact_list import ContactListWidget
from client.tui.widgets.message_list import MessageListWidget
from client.tui.widgets.chat_input import ChatInput
from client.utils.logger import get_logger

logger = get_logger(__name__)


class ChatScreen(Screen):
    """Main chat screen with contact list and message display."""

    CSS = """
    ChatScreen {
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 3fr;
    }

    #contact-list {
        column-span: 1;
        row-span: 1;
        background: $surface;
        border: solid $primary;
        overflow-y: scroll;
    }

    #contact-header {
        background: $primary;
        color: $text;
        padding: 1;
        text-align: center;
    }

    #chat-area {
        column-span: 1;
        row-span: 1;
        layout: vertical;
    }

    #chat-header {
        background: $primary;
        color: $text;
        padding: 1;
        text-align: center;
    }

    #message-list {
        height: 1fr;
        background: $surface;
        border: solid $primary;
        overflow-y: scroll;
    }

    #input-area {
        height: auto;
        background: $surface;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+n", "add_contact", "Add Contact", show=True),
        Binding("ctrl+k", "show_my_key", "My Key", show=True),
        Binding("ctrl+r", "refresh", "Refresh", show=True),
    ]

    def __init__(
        self,
        chat_service: ChatService,
        contact_service: ContactService,
        **kwargs
    ) -> None:
        """Initialize the chat screen.

        Args:
            chat_service: Service for chat operations.
            contact_service: Service for contact operations.
            **kwargs: Additional keyword arguments for Screen.
        """
        super().__init__(**kwargs)
        self.chat_service = chat_service
        self.contact_service = contact_service
        self.current_contact: Optional[Contact] = None

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield Header()

        # Contact list on the left
        with Container(id="contact-list"):
            yield Label("Contacts", id="contact-header")
            yield ContactListWidget(id="contacts")

        # Chat area on the right
        with Container(id="chat-area"):
            yield Label("Select a contact to start chatting", id="chat-header")
            yield MessageListWidget(self.chat_service, id="message-list")
            with Horizontal(id="input-area"):
                yield ChatInput(id="chat-input")
                yield Button("Send", id="send-btn", variant="primary")

        yield Footer()

    async def on_mount(self) -> None:
        """Handle screen mount event."""
        # Load contacts
        await self._load_contacts()

        # Start message polling
        self.chat_service.start_message_polling(
            on_message=self._on_message_received
        )

        logger.info("Chat screen mounted, polling started")

    async def on_unmount(self) -> None:
        """Handle screen unmount event."""
        await self.chat_service.stop_message_polling()
        logger.info("Chat screen unmounted, polling stopped")

    async def _load_contacts(self) -> None:
        """Load contacts from database."""
        contacts = self.contact_service.get_all_contacts()
        contact_list = self.query_one("#contacts", ContactListWidget)
        contact_list.update_contacts(contacts)
        logger.info(f"Loaded {len(contacts)} contacts")

    def on_contact_list_widget_contact_selected(
        self, event: ContactListWidget.ContactSelected
    ) -> None:
        """Handle contact selection event."""
        self.current_contact = event.contact
        asyncio.create_task(self._load_messages())

    async def _load_messages(self) -> None:
        """Load messages for the current contact."""
        if not self.current_contact:
            return

        # Update header
        header = self.query_one("#chat-header", Label)
        header.update(f"Chatting with: {self.current_contact.alias}")

        # Load messages
        message_list = self.query_one("#message-list", MessageListWidget)
        await message_list.load_messages(self.current_contact)

        logger.debug(f"Loaded messages for {self.current_contact.alias}")

    def _on_message_received(self, message: Message, _: str) -> None:
        """Handle received message from polling.

        Args:
            message: The received message.
            _: Placeholder for plaintext (will be decrypted here).
        """
        # Schedule async handling
        asyncio.create_task(self._handle_received_message_async(message))

    async def _handle_received_message_async(self, message: Message) -> None:
        """Async handler for received messages.

        Args:
            message: The received message.
        """
        # Get sender contact
        sender = self.contact_service.get_contact(message.sender_id)

        if sender is None:
            logger.warning(f"Received message from unknown sender: {message.sender_id} — ignoring")
            return

        # Decrypt message
        try:
            plaintext = await self.chat_service.decrypt_message(message, sender)
        except Exception as e:
            logger.error(f"Failed to decrypt message from {sender.alias}: {e}")
            plaintext = "[decryption failed]"

        # Update display if this is the current conversation
        if self.current_contact and message.sender_id == self.current_contact.user_id:
            message_list = self.query_one("#message-list", MessageListWidget)
            await message_list.add_message(message, plaintext)
            logger.debug(f"Displayed message from {sender.alias}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "send-btn":
            asyncio.create_task(self._send_message())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        if event.input.id == "chat-input":
            asyncio.create_task(self._send_message())

    async def _send_message(self) -> None:
        """Send a message to the current contact."""
        if not self.current_contact:
            self.notify("Select a contact first", severity="warning")
            return

        chat_input = self.query_one("#chat-input", ChatInput)
        message_text = chat_input.value.strip()

        if not message_text:
            return

        # Send message
        try:
            message = await self.chat_service.send_message(
                self.current_contact, message_text
            )
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            self.notify(f"Failed to send: {e}", severity="error")
            return

        # Clear input
        chat_input.value = ""

        # Update display
        message_list = self.query_one("#message-list", MessageListWidget)
        await message_list.add_message(message, message_text)

        # Notify user
        if message.status == MessageStatus.QUEUED:
            self.notify("Message queued on server", severity="information")
        else:
            self.notify("Message could not be queued", severity="warning")

        logger.debug(f"Sent message to {self.current_contact.alias}")

    def action_add_contact(self) -> None:
        """Open add contact dialog."""
        from client.tui.screens.add_contact_screen import AddContactScreen

        def on_contact_added(contact: Optional[Contact]) -> None:
            if contact:
                self.notify(f"Contact added: {contact.alias}")
                asyncio.create_task(self._load_contacts())

        self.app.push_screen(AddContactScreen(self.contact_service), on_contact_added)

    def action_show_my_key(self) -> None:
        """Show the user's own public key for sharing."""
        from client.tui.screens.my_key_screen import MyKeyScreen

        user_id = self.chat_service.user_id
        public_key_b64 = self.chat_service.key_manager.public_key_base64
        self.app.push_screen(MyKeyScreen(user_id, public_key_b64))

    def action_refresh(self) -> None:
        """Refresh contacts and messages."""
        asyncio.create_task(self._load_contacts())
        if self.current_contact:
            asyncio.create_task(self._load_messages())
        self.notify("Refreshed", severity="information")
