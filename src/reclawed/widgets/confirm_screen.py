"""Reusable confirmation modal screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ConfirmScreen(ModalScreen[bool]):
    """Modal that asks the user to confirm or cancel an action.

    Dismisses with ``True`` if confirmed, ``False`` otherwise.
    Arrow keys switch focus between buttons. Enter confirms the focused button.
    """

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }
    ConfirmScreen > #confirm-dialog {
        width: 50;
        height: auto;
        max-height: 12;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    ConfirmScreen #confirm-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    ConfirmScreen #confirm-message {
        width: 100%;
        margin-bottom: 1;
    }
    ConfirmScreen #confirm-buttons {
        width: 100%;
        height: 3;
        align: center middle;
    }
    ConfirmScreen #confirm-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("left", "focus_previous", "", show=False),
        Binding("right", "focus_next", "", show=False),
        Binding("y", "confirm_yes", "", show=False),
        Binding("n", "cancel", "", show=False),
    ]

    def __init__(self, title: str, message: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._message = message

    def compose(self) -> ComposeResult:
        with Static(id="confirm-dialog"):
            yield Label(self._title, id="confirm-title")
            yield Label(self._message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes", id="btn-yes", variant="error")
                yield Button("Cancel", id="btn-cancel", variant="default")

    def on_mount(self) -> None:
        # Focus the Yes button by default
        self.query_one("#btn-yes", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm_yes(self) -> None:
        self.dismiss(True)
