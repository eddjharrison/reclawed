"""Tiny picker modal for choosing Create Group vs Join Group."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class GroupMenuScreen(ModalScreen[str | None]):
    """Two-button modal: 'Create Group' or 'Join Group'.

    Dismisses with:
    - ``"create"`` if the user picks Create Group
    - ``"join"`` if the user picks Join Group
    - ``None`` if cancelled (Escape)
    """

    DEFAULT_CSS = """
    GroupMenuScreen {
        align: center middle;
    }
    GroupMenuScreen > Vertical {
        width: 40;
        height: auto;
        padding: 2 3;
        background: $surface;
        border: tall $primary;
    }
    GroupMenuScreen #title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    GroupMenuScreen Button {
        width: 100%;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Group Chat", id="title")
            yield Button("Create Group", id="btn-create", variant="primary")
            yield Button("Join Group", id="btn-join", variant="default")
            yield Button("Cancel", id="btn-cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-create":
            self.dismiss("create")
        elif event.button.id == "btn-join":
            self.dismiss("join")
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
