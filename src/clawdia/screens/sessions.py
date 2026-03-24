"""Session picker modal screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static

from clawdia.store import Store


class SessionPickerScreen(ModalScreen[str | None]):
    """Modal for picking a previous session to resume."""

    DEFAULT_CSS = """
    SessionPickerScreen {
        align: center middle;
    }
    SessionPickerScreen > #session-dialog {
        width: 60;
        height: 20;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    SessionPickerScreen #session-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store
        self._sessions = store.list_sessions()

    def compose(self) -> ComposeResult:
        with Static(id="session-dialog"):
            yield Label("Sessions", id="session-title")
            items = []
            for s in self._sessions:
                ts = s.updated_at.strftime("%Y-%m-%d %H:%M")
                label = f"{s.name} ({s.message_count} msgs) - {ts}"
                item = ListItem(Label(label))
                item._session_id = s.id  # type: ignore[attr-defined]
                items.append(item)
            if not items:
                items.append(ListItem(Label("No sessions yet")))
            yield ListView(*items, id="session-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        session_id = getattr(event.item, "_session_id", None)
        if session_id:
            self.dismiss(session_id)

    def action_cancel(self) -> None:
        self.dismiss(None)
