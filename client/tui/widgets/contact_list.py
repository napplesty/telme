"""Contact list widget for displaying contacts."""
from typing import List, Optional

from textual.message import Message
from textual.widgets import ListView, ListItem, Label, Static

from client.storage.models import Contact
from client.utils.logger import get_logger

logger = get_logger(__name__)


class ContactListWidget(ListView):
    """Widget for displaying and selecting contacts."""

    class ContactSelected(Message):
        """Message sent when a contact is selected.

        Named ContactSelected (not Selected) to avoid shadowing
        ListView.Selected, which would break ListView's internal
        click/keyboard handling.
        """

        def __init__(self, contact: Contact) -> None:
            self.contact = contact
            super().__init__()

    class Empty(Static):
        """Widget displayed when no contacts exist."""

        def __init__(self) -> None:
            super().__init__("No contacts yet.\nPress Ctrl+N to add one.")

    def __init__(self, contacts: Optional[List[Contact]] = None, **kwargs) -> None:
        """Initialize the contact list widget.

        Args:
            contacts: Initial list of contacts.
            **kwargs: Additional keyword arguments for ListView.
        """
        super().__init__(**kwargs)
        self._contacts: List[Contact] = contacts or []

    @property
    def contacts(self) -> List[Contact]:
        """Get the list of contacts."""
        return self._contacts

    @property
    def current_contact(self) -> Optional[Contact]:
        """Get the currently selected contact."""
        if self.index is not None and 0 <= self.index < len(self._contacts):
            return self._contacts[self.index]
        return None

    def update_contacts(self, contacts: List[Contact]) -> None:
        """Update the contact list.

        Args:
            contacts: New list of contacts.
        """
        self.clear()
        self._contacts = contacts

        if not contacts:
            # Show empty state
            self.append(ListItem(self.Empty()))
            return

        for contact in contacts:
            # Create list item with contact info
            item = ListItem(
                Label(contact.alias, classes="contact-name"),
                Label(contact.user_id[:12] + "...", classes="contact-id"),
                classes="contact-item"
            )
            self.append(item)

        logger.debug(f"Updated contact list with {len(contacts)} contacts")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list selection event."""
        if self.index is not None and 0 <= self.index < len(self._contacts):
            contact = self._contacts[self.index]
            logger.debug(f"Contact selected: {contact.alias}")
            self.post_message(self.ContactSelected(contact))

    def get_contact_by_user_id(self, user_id: str) -> Optional[Contact]:
        """Get a contact by user ID.

        Args:
            user_id: The user ID to search for.

        Returns:
            Contact or None if not found.
        """
        for contact in self._contacts:
            if contact.user_id == user_id:
                return contact
        return None
