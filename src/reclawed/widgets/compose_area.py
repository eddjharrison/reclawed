"""Compose area with text input and send functionality."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.events import Key
from textual.message import Message as TMessage
from textual.widgets import Button, TextArea


class ComposeInput(TextArea):
    """TextArea that sends on Enter and inserts newline on Shift+Enter."""

    class SendRequested(TMessage):
        """Posted when user presses Enter (without modifiers)."""

    def _on_key(self, event: Key) -> None:
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.post_message(self.SendRequested())
        elif event.key == "shift+enter":
            event.prevent_default()
            event.stop()
            self.insert("\n")


class ComposeArea(Horizontal):
    """Text input area with send button."""

    DEFAULT_CSS = """
    ComposeArea {
        width: 100%;
        height: auto;
        min-height: 3;
        max-height: 10;
        dock: bottom;
        padding: 0 1;
    }
    ComposeArea ComposeInput {
        width: 1fr;
        min-height: 3;
        max-height: 8;
    }
    ComposeArea Button {
        width: 10;
        min-height: 3;
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    class Submitted(TMessage):
        """Posted when the user submits a message."""
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def compose(self) -> ComposeResult:
        yield ComposeInput(id="compose-input")
        yield Button("Send", id="send-btn", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#compose-input", ComposeInput).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            self._submit()

    def on_compose_input_send_requested(self) -> None:
        self._submit()

    def _submit(self) -> None:
        ta = self.query_one("#compose-input", ComposeInput)
        text = ta.text.strip()
        if text:
            self.post_message(self.Submitted(text))
            ta.clear()

    def insert_quote(self, text: str) -> None:
        """Insert a blockquote into the compose area."""
        ta = self.query_one("#compose-input", ComposeInput)
        quoted = "\n".join(f"> {line}" for line in text.splitlines())
        current = ta.text
        if current:
            ta.load_text(f"{current}\n{quoted}\n\n")
        else:
            ta.load_text(f"{quoted}\n\n")
        ta.focus()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the compose area."""
        ta = self.query_one("#compose-input", ComposeInput)
        btn = self.query_one("#send-btn", Button)
        ta.disabled = not enabled
        btn.disabled = not enabled
