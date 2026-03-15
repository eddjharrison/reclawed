"""Search overlay modal screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

from reclawed.store import Store


class SearchScreen(ModalScreen[str | None]):
    """Modal search overlay for finding messages."""

    DEFAULT_CSS = """
    SearchScreen {
        align: center middle;
    }
    SearchScreen > #search-dialog {
        width: 70;
        height: 24;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    SearchScreen #search-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    SearchScreen #search-input {
        width: 100%;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, store: Store, session_id: str | None = None) -> None:
        super().__init__()
        self.store = store
        self._session_id = session_id

    def compose(self) -> ComposeResult:
        with Static(id="search-dialog"):
            yield Label("Search Messages", id="search-title")
            yield Input(placeholder="Type to search...", id="search-input")
            yield ListView(id="search-results")

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    async def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        results_view = self.query_one("#search-results", ListView)
        await results_view.clear()

        if len(query) < 2:
            return

        results = self.store.search_messages(query, self._session_id)
        for msg in results[:20]:
            preview = msg.content[:80].replace("\n", " ")
            role = "You" if msg.role == "user" else "Claude"
            ts = msg.timestamp.strftime("%H:%M")
            label = f"[{role} {ts}] {preview}"
            item = ListItem(Label(label))
            item._message_id = msg.id  # type: ignore[attr-defined]
            await results_view.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        message_id = getattr(event.item, "_message_id", None)
        if message_id:
            self.dismiss(message_id)

    def action_cancel(self) -> None:
        self.dismiss(None)
