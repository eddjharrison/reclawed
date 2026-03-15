"""Single row in the chat sidebar representing one session."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Click
from textual.message import Message as TMessage
from textual.widgets import Label

from reclawed.models import Session
from reclawed.utils import format_relative_time


_PREVIEW_MAX = 40


class ChatListItem(Vertical):
    """Displays one session as a two-line sidebar row using Label widgets.

    Line 1: session name + relative timestamp
    Line 2: last message preview + unread badge
    """

    DEFAULT_CSS = """
    ChatListItem {
        width: 100%;
        height: 3;
        padding: 0 1;
        background: $surface;
        border-bottom: solid $primary 20%;
    }
    ChatListItem:hover {
        background: $primary-background;
    }
    ChatListItem.active {
        background: $primary 20%;
        border-left: thick $accent;
    }
    ChatListItem .chat-name {
        width: 100%;
        color: $text;
    }
    ChatListItem .chat-preview {
        width: 100%;
        color: $text-muted;
    }
    ChatListItem.unread .chat-name {
        text-style: bold;
    }
    ChatListItem.muted .chat-name {
        color: $text-muted;
    }
    """

    class Clicked(TMessage):
        """Posted when this row is clicked."""

        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    class ContextMenuRequested(TMessage):
        """Posted on right-click for context menu."""

        def __init__(self, session_id: str, is_muted: bool) -> None:
            super().__init__()
            self.session_id = session_id
            self.is_muted = is_muted

    def __init__(
        self,
        session: Session,
        last_preview: str = "",
        is_active: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._session = session
        self._last_preview = last_preview
        self._is_active = is_active

        if is_active:
            self.add_class("active")
        if session.unread_count > 0:
            self.add_class("unread")
        if session.muted:
            self.add_class("muted")

    @property
    def session_id(self) -> str:
        return self._session.id

    @staticmethod
    def _build_content(session: Session, preview_text: str) -> str:
        """Build a display string (used by tests)."""
        ts = format_relative_time(session.updated_at)
        name = session.name
        preview = preview_text.replace("\n", " ")
        if len(preview) > _PREVIEW_MAX:
            preview = preview[:_PREVIEW_MAX - 1] + "…"
        return f"{name}  {ts}\n{preview}"

    def compose(self) -> ComposeResult:
        ts = format_relative_time(self._session.updated_at)
        name = self._session.name
        if self._session.muted:
            name = f"(muted) {name}"

        yield Label(f"{name}  {ts}", classes="chat-name")

        preview = self._last_preview.replace("\n", " ")
        if len(preview) > _PREVIEW_MAX:
            preview = preview[:_PREVIEW_MAX - 1] + "…"
        badge = f" ({self._session.unread_count})" if self._session.unread_count > 0 else ""
        yield Label(f"{preview}{badge}", classes="chat-preview")

    def refresh_data(
        self,
        session: Session | None = None,
        last_preview: str | None = None,
        is_active: bool | None = None,
    ) -> None:
        if session is not None:
            self._session = session
        if last_preview is not None:
            self._last_preview = last_preview
        if is_active is not None:
            self._is_active = is_active
            if is_active:
                self.add_class("active")
            else:
                self.remove_class("active")

        if self._session.unread_count > 0:
            self.add_class("unread")
        else:
            self.remove_class("unread")

        if self._session.muted:
            self.add_class("muted")
        else:
            self.remove_class("muted")

        # Update label text
        try:
            labels = self.query(Label)
            label_list = list(labels)
            if len(label_list) >= 2:
                ts = format_relative_time(self._session.updated_at)
                name = self._session.name
                if self._session.muted:
                    name = f"(muted) {name}"
                label_list[0].update(f"{name}  {ts}")

                preview = self._last_preview.replace("\n", " ")
                if len(preview) > _PREVIEW_MAX:
                    preview = preview[:_PREVIEW_MAX - 1] + "…"
                badge = f" ({self._session.unread_count})" if self._session.unread_count > 0 else ""
                label_list[1].update(f"{preview}{badge}")
        except Exception:
            pass

    def on_click(self, event: Click) -> None:
        event.stop()
        self.post_message(self.Clicked(self._session.id))
