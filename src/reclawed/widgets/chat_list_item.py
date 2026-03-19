"""Single row in the chat sidebar representing one session."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Click, Key
from textual.message import Message as TMessage
from textual.widgets import Input, Label

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
        color: $text;
    }
    ChatListItem.unread .chat-preview {
        color: $success;
        text-style: bold;
    }
    ChatListItem.unread {
        border-left: thick $success;
    }
    ChatListItem.muted .chat-name {
        color: $text-muted;
    }
    ChatListItem.group .chat-name {
        color: $accent;
    }
    ChatListItem.worker {
        padding-left: 3;
    }
    ChatListItem.worker .chat-name {
        color: $text-muted;
    }
    ChatListItem.orchestrator .chat-name {
        color: $warning;
        text-style: bold;
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

    class Renamed(TMessage):
        """Posted when the user completes an inline rename."""

        def __init__(self, session_id: str, new_name: str) -> None:
            super().__init__()
            self.session_id = session_id
            self.new_name = new_name

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
        if session.is_group:
            self.add_class("group")
        if session.session_type == "worker":
            self.add_class("worker")
        if session.session_type == "orchestrator":
            self.add_class("orchestrator")

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

    @staticmethod
    def _format_name(session: Session) -> str:
        """Build the display name with type/status prefixes."""
        name = session.name
        if session.session_type == "worker":
            icon = "\u2713" if session.worker_status == "complete" else "\u27f3"
            name = f"{icon} [W] {name}"
        elif session.is_group:
            name = f"[G] {name}"
        if session.muted:
            name = f"(muted) {name}"
        return name

    def compose(self) -> ComposeResult:
        ts = format_relative_time(self._session.updated_at)
        name = self._format_name(self._session)

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

        if self._session.is_group:
            self.add_class("group")
        else:
            self.remove_class("group")

        if self._session.session_type == "worker":
            self.add_class("worker")
        else:
            self.remove_class("worker")
        if self._session.session_type == "orchestrator":
            self.add_class("orchestrator")
        else:
            self.remove_class("orchestrator")

        # Update label text
        try:
            labels = self.query(Label)
            label_list = list(labels)
            if len(label_list) >= 2:
                ts = format_relative_time(self._session.updated_at)
                name = self._format_name(self._session)
                label_list[0].update(f"{name}  {ts}")

                preview = self._last_preview.replace("\n", " ")
                if len(preview) > _PREVIEW_MAX:
                    preview = preview[:_PREVIEW_MAX - 1] + "…"
                badge = f" ({self._session.unread_count})" if self._session.unread_count > 0 else ""
                label_list[1].update(f"{preview}{badge}")
        except Exception:
            pass

    async def start_rename(self) -> None:
        """Replace the name label with an Input for inline editing."""
        try:
            labels = list(self.query(Label))
            if not labels:
                return
            name_label = labels[0]
            name_label.display = False
            rename_input = Input(
                value=self._session.name,
                id="rename-input",
                classes="chat-name",
            )
            await self.mount(rename_input, before=name_label)
            rename_input.focus()
        except Exception:
            pass

    def _finish_rename(self, new_name: str) -> None:
        """Complete the rename and restore the label."""
        try:
            rename_input = self.query_one("#rename-input", Input)
            rename_input.remove()
        except Exception:
            pass
        try:
            labels = list(self.query(Label))
            if labels:
                labels[0].display = True
        except Exception:
            pass
        name = new_name.strip()
        if name and name != self._session.name:
            self.post_message(self.Renamed(self._session.id, name))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "rename-input":
            event.stop()
            self._finish_rename(event.value)

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            try:
                self.query_one("#rename-input", Input)
                event.stop()
                self._finish_rename(self._session.name)  # cancel = restore original
            except Exception:
                pass

    def on_click(self, event: Click) -> None:
        event.stop()
        self.post_message(self.Clicked(self._session.id))
