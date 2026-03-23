"""Workspace picker modal for creating a new chat in a specific workspace."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static

from reclawed.config import Workspace

# Sentinel value for the Default workspace (no cwd).
PICK_DEFAULT = "_default"


class WorkspacePicker(ModalScreen[str | None]):
    """Modal that lets the user pick a workspace to create a new chat in.

    Dismisses with:
    - A workspace ``expanded_path`` string for a real workspace
    - ``PICK_DEFAULT`` for the Default (no-cwd) workspace
    - ``None`` on cancel
    """

    DEFAULT_CSS = """
    WorkspacePicker {
        align: center middle;
    }
    WorkspacePicker > #picker-dialog {
        width: 50;
        height: auto;
        max-height: 20;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    WorkspacePicker #picker-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: $text-muted;
        margin-bottom: 1;
    }
    WorkspacePicker ListView {
        width: 100%;
        height: auto;
        border: none;
        background: $surface;
    }
    WorkspacePicker ListItem {
        padding: 0 1;
    }
    WorkspacePicker ListItem:hover {
        background: $primary 30%;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, workspaces: list[Workspace], **kwargs) -> None:
        super().__init__(**kwargs)
        self._workspaces = workspaces

    def compose(self) -> ComposeResult:
        items: list[ListItem] = []

        # Default workspace (no cwd)
        default_item = ListItem(Label("Default"), id="ws-default")
        default_item._ws_cwd = PICK_DEFAULT  # type: ignore[attr-defined]
        items.append(default_item)

        for i, ws in enumerate(self._workspaces):
            item = ListItem(Label(ws.name), id=f"ws-{i}")
            item._ws_cwd = ws.expanded_path  # type: ignore[attr-defined]
            items.append(item)

        with Static(id="picker-dialog"):
            yield Label("New Chat in Workspace", id="picker-title")
            yield ListView(*items, id="picker-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        cwd = getattr(event.item, "_ws_cwd", PICK_DEFAULT)
        self.dismiss(cwd)

    def action_cancel(self) -> None:
        self.dismiss(None)
