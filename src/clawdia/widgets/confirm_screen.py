"""Reusable confirmation modal screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ConfirmScreen(ModalScreen[bool]):
    """Modal that asks the user to confirm or cancel an action.

    Dismisses with ``True`` if confirmed, ``False`` otherwise.
    Arrow keys switch focus between buttons. y/n/Escape as shortcuts.
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
        self.query_one("#btn-yes", Button).focus()

    def on_key(self, event: Key) -> None:
        if event.key == "y":
            event.stop()
            self.dismiss(True)
        elif event.key in ("n", "escape"):
            event.stop()
            self.dismiss(False)
        elif event.key in ("left", "right", "tab"):
            event.stop()
            focused = self.app.focused
            if focused and focused.id == "btn-yes":
                self.query_one("#btn-cancel", Button).focus()
            else:
                self.query_one("#btn-yes", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")
