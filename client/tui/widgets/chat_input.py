"""Chat input widget for message composition."""
from textual.widgets import Input

from client.utils.logger import get_logger

logger = get_logger(__name__)


class ChatInput(Input):
    """Input widget for composing chat messages."""

    DEFAULT_CSS = """
    ChatInput {
        width: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        """Initialize the chat input widget.

        Args:
            **kwargs: Additional keyword arguments for Input.
        """
        super().__init__(
            placeholder="Type your message... (Enter to send)",
            **kwargs
        )

    def clear(self) -> None:
        """Clear the input field."""
        self.value = ""
