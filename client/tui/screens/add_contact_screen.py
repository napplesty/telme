"""Modal screen for adding new contacts."""
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from client.services.contact_service import ContactService
from client.storage.models import Contact
from client.utils.logger import get_logger

logger = get_logger(__name__)


class AddContactScreen(ModalScreen[Optional[Contact]]):
    """Modal screen for adding a new contact."""

    CSS = """
    AddContactScreen {
        align: center middle;
    }

    .dialog {
        width: 60;
        height: auto;
        max-height: 20;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }

    .dialog-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    .dialog-content {
        margin: 1;
    }

    Input {
        width: 100%;
        margin-bottom: 1;
    }

    .button-row {
        align: center middle;
        height: auto;
        margin-top: 1;
    }

    Button {
        margin: 0 1;
    }

    .hint {
        color: $text-muted;
        text-style: italic;
        text-align: center;
        margin-top: 1;
    }

    .error {
        color: $error;
        text-align: center;
        margin-top: 1;
    }
    """

    def __init__(self, contact_service: ContactService, **kwargs) -> None:
        """Initialize the add contact screen.

        Args:
            contact_service: Service for contact operations.
            **kwargs: Additional keyword arguments for ModalScreen.
        """
        super().__init__(**kwargs)
        self.contact_service = contact_service

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        with Container(classes="dialog"):
            yield Label("Add New Contact", classes="dialog-title")

            with Container(classes="dialog-content"):
                yield Input(
                    placeholder="Contact alias (e.g., Alice)",
                    id="alias-input",
                )
                yield Input(
                    placeholder="Public Key (base64 encoded)",
                    id="public-key-input",
                )
                yield Label(
                    "Tip: Ask your contact to share their public key. "
                    "Press Ctrl+K to view your own key.",
                    classes="hint"
                )
                yield Label("", id="error-label", classes="error")

            with Horizontal(classes="button-row"):
                yield Button("Add", id="add-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "add-btn":
            self._add_contact()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        if event.input.id == "public-key-input":
            self._add_contact()

    def _add_contact(self) -> None:
        """Add the contact."""
        alias_input = self.query_one("#alias-input", Input)
        public_key_input = self.query_one("#public-key-input", Input)
        error_label = self.query_one("#error-label", Label)

        alias = alias_input.value.strip()
        public_key = public_key_input.value.strip()

        # Validate inputs
        if not alias:
            error_label.update("Please enter an alias")
            return

        if not public_key:
            error_label.update("Please enter a public key")
            return

        if len(alias) < 2:
            error_label.update("Alias must be at least 2 characters")
            return

        # Add contact via service
        contact = self.contact_service.add_contact(public_key, alias)
        logger.info(f"Contact added: {alias}")
        self.dismiss(contact)

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.dismiss(None)
