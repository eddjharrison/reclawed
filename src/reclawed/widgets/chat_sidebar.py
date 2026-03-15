"""Sidebar container listing all chat sessions with live search filtering."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message as TMessage
from textual.widgets import Input, Static

from reclawed.models import Session
from reclawed.store import Store
from reclawed.widgets.chat_list_item import ChatListItem


class ChatSidebar(Vertical):
    """Left-hand sidebar that lists sessions and supports search filtering.

    Layout::

        Vertical (ChatSidebar)
          Input  (search)
          VerticalScroll (chat-list)
            ChatListItem ...
            ChatListItem ...

    Messages posted:
    - ``ChatSidebar.SessionSelected(session_id)`` when a row is clicked
    - ``ChatSidebar.NewChatRequested()``          when Ctrl+N is pressed
    """

    DEFAULT_CSS = """
    ChatSidebar {
        width: 35;
        height: 100%;
        background: $surface;
        border-right: solid $primary 30%;
    }
    ChatSidebar Input {
        width: 100%;
        height: 3;
        border: solid $primary 30%;
        background: $surface;
    }
    ChatSidebar #chat-list {
        width: 100%;
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+n", "new_chat", "New Chat", show=True),
        Binding("m", "context_menu", "Menu", show=False),
    ]

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    class SessionSelected(TMessage):
        """Posted when the user clicks a session row."""

        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    class NewChatRequested(TMessage):
        """Posted when the user wants to start a new chat."""

    class ContextMenuRequested(TMessage):
        """Posted when a context menu is requested on a session."""

        def __init__(self, session_id: str, is_muted: bool) -> None:
            super().__init__()
            self.session_id = session_id
            self.is_muted = is_muted

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, store: Store, **kwargs) -> None:
        super().__init__(**kwargs)
        self._store = store
        # Ordered list of all sessions (refreshed from the store)
        self._sessions: list[Session] = []
        # Map session_id -> last assistant/user message preview
        self._previews: dict[str, str] = {}
        # The session_id that is currently open in the chat pane
        self._active_id: str | None = None
        # Current search query (lowercased)
        self._search_query: str = ""

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search chats...", id="sidebar-search")
        yield VerticalScroll(id="chat-list")

    def on_mount(self) -> None:
        self.refresh_sessions()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh_sessions(self, active_session_id: str | None = None) -> None:
        """Re-query the store and rebuild the chat list.

        Call this after any session-level mutation (new session, rename, delete,
        etc.).  ``active_session_id`` sets which row is highlighted; passing
        ``None`` keeps the previous active session.
        """
        if active_session_id is not None:
            self._active_id = active_session_id

        all_sessions = self._store.list_sessions()
        # Hide empty sessions (no messages) unless they're the active one
        self._sessions = [
            s for s in all_sessions
            if s.message_count > 0 or s.id == self._active_id
        ]

        # Build preview text for each session from its last message.
        self._previews.clear()
        for session in self._sessions:
            last = self._store.get_last_message(session.id)
            self._previews[session.id] = last.content if last is not None else ""

        self._rebuild_list()

    def set_active(self, session_id: str) -> None:
        """Highlight ``session_id`` as the currently open session."""
        self._active_id = session_id
        chat_list = self.query_one("#chat-list", VerticalScroll)
        for item in chat_list.query(ChatListItem):
            is_active = item.session_id == session_id
            if is_active:
                item.refresh_data(is_active=True)
                item.scroll_visible()
            else:
                item.refresh_data(is_active=False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_list(self) -> None:
        """Clear and repopulate the scroll pane, honouring the search filter."""
        chat_list = self.query_one("#chat-list", VerticalScroll)
        chat_list.remove_children()

        visible = self._filtered_sessions()
        for session in visible:
            preview = self._previews.get(session.id, "")
            is_active = session.id == self._active_id
            chat_list.mount(
                ChatListItem(session, last_preview=preview, is_active=is_active)
            )

    def _filtered_sessions(self) -> list[Session]:
        """Return sessions matching the current search query (case-insensitive)."""
        if not self._search_query:
            return list(self._sessions)
        q = self._search_query
        return [s for s in self._sessions if q in s.name.lower()]

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "sidebar-search":
            self._search_query = event.value.strip().lower()
            self._rebuild_list()

    def on_chat_list_item_clicked(self, event: ChatListItem.Clicked) -> None:
        event.stop()
        self.post_message(self.SessionSelected(event.session_id))

    def on_chat_list_item_context_menu_requested(self, event: ChatListItem.ContextMenuRequested) -> None:
        event.stop()
        self.post_message(self.ContextMenuRequested(event.session_id, event.is_muted))

    def action_new_chat(self) -> None:
        self.post_message(self.NewChatRequested())

    def action_context_menu(self) -> None:
        """Open context menu for the active session in the sidebar."""
        if self._active_id:
            session = next((s for s in self._sessions if s.id == self._active_id), None)
            if session:
                self.post_message(self.ContextMenuRequested(session.id, session.muted))
