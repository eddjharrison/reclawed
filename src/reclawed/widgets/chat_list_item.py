"""Single row in the chat sidebar representing one session."""

from __future__ import annotations

from textual.events import Click
from textual.message import Message as TMessage
from textual.widgets import Static
from rich.text import Text

from reclawed.models import Session
from reclawed.utils import format_relative_time


_PREVIEW_MAX = 40


class ChatListItem(Static):
    """Displays one session as a two-line sidebar row.

    Line 1: session name (left) + relative timestamp (right)
    Line 2: last message preview truncated to ~40 chars (left) + unread badge (right)

    Visual classes:
      ``.active``  -- currently open session (highlighted background)
      ``.unread``  -- bold name + coloured timestamp
      ``.muted``   -- shows muted indicator next to the name
    """

    DEFAULT_CSS = """
    ChatListItem {
        width: 100%;
        height: 4;
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
    ChatListItem.unread .sidebar-name {
        text-style: bold;
    }
    ChatListItem.unread .sidebar-timestamp {
        color: $accent;
    }
    ChatListItem.muted {
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

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._render_content()

    def _render_content(self) -> None:
        """Build the two-line Rich Text and push it to the Static renderer."""
        session = self._session
        ts_str = format_relative_time(session.updated_at)

        # --- Line 1: name (left) + timestamp (right) ---
        name_display = session.name
        if session.muted:
            name_display = f"[muted] {name_display}"

        line1 = Text(overflow="fold", no_wrap=True)
        line1.append(name_display, style="bold" if session.unread_count > 0 else "")
        # Right-align timestamp by padding -- we pad at render time with justify
        line1.append(f"  {ts_str}", style="dim" if session.unread_count == 0 else "$accent")

        # --- Line 2: preview (left) + unread badge (right) ---
        preview = self._last_preview.replace("\n", " ")
        if len(preview) > _PREVIEW_MAX:
            preview = preview[:_PREVIEW_MAX - 1] + "\u2026"  # ellipsis char

        line2 = Text(overflow="fold", no_wrap=True)
        line2.append(preview, style="dim")
        if session.unread_count > 0:
            badge = f"  [{session.unread_count}]"
            line2.append(badge, style="bold green")

        combined = Text()
        combined.append_text(line1)
        combined.append("\n")
        combined.append_text(line2)

        self.update(combined)

    def refresh_data(
        self,
        session: Session | None = None,
        last_preview: str | None = None,
        is_active: bool | None = None,
    ) -> None:
        """Update the item's data and re-render.

        Pass only the arguments that have changed; ``None`` values are ignored.
        """
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

        # Sync CSS state classes from model
        if self._session.unread_count > 0:
            self.add_class("unread")
        else:
            self.remove_class("unread")

        if self._session.muted:
            self.add_class("muted")
        else:
            self.remove_class("muted")

        self._render_content()

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def on_click(self, event: Click) -> None:
        event.stop()
        self.post_message(self.Clicked(self._session.id))
