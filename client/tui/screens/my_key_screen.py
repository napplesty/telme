"""Modal screen for displaying the user's own public key."""
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from client.utils.logger import get_logger

logger = get_logger(__name__)


class MyKeyScreen(ModalScreen[None]):
    """Modal screen showing the user's public key for sharing with contacts."""

    CSS = """
    MyKeyScreen {
        align: center middle;
    }

    .dialog {
        width: 72;
        height: auto;
        max-height: 18;
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

    .key-label {
        color: $text-muted;
        margin-bottom: 0;
    }

    .key-value {
        color: $success;
        text-style: bold;
        margin-bottom: 1;
    }

    .hint {
        color: $text-muted;
        text-style: italic;
        text-align: center;
        margin-top: 1;
    }

    .button-row {
        align: center middle;
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(self, user_id: str, public_key_b64: str, **kwargs) -> None:
        """Initialize the my-key screen.

        Args:
            user_id: The current user's ID (SHA256 hash).
            public_key_b64: The current user's base64-encoded public key.
            **kwargs: Additional keyword arguments for ModalScreen.
        """
        super().__init__(**kwargs)
        self._user_id = user_id
        self._public_key_b64 = public_key_b64

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        with Container(classes="dialog"):
            yield Label("My Public Key", classes="dialog-title")

            with Container(classes="dialog-content"):
                yield Label("User ID:", classes="key-label")
                yield Static(self._user_id, classes="key-value")

                yield Label("Public Key (share this with your contacts):", classes="key-label")
                yield Static(self._public_key_b64, classes="key-value")

                yield Label(
                    "Your contact needs this public key to add you.\n"
                    "Copy it and send it through a trusted channel.",
                    classes="hint",
                )

            with Horizontal(classes="button-row"):
                yield Button("Close", id="close-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "close-btn":
            self.dismiss(None)

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.dismiss(None)
