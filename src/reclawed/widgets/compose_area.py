"""Compose area with text input and send functionality."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message as TMessage
from textual.widgets import Button, TextArea


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
    ComposeArea TextArea {
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
        yield TextArea(id="compose-input")
        yield Button("Send", id="send-btn", variant="primary")

    def on_mount(self) -> None:
        ta = self.query_one("#compose-input", TextArea)
        ta.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            self._submit()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        pass

    def _on_key(self, event) -> None:
        """Handle Enter to send (without shift/ctrl modifiers)."""
        if event.key == "enter" and not event.shift and not event.ctrl:
            event.prevent_default()
            event.stop()
            self._submit()

    def _submit(self) -> None:
        ta = self.query_one("#compose-input", TextArea)
        text = ta.text.strip()
        if text:
            self.post_message(self.Submitted(text))
            ta.clear()

    def insert_quote(self, text: str) -> None:
        """Insert a blockquote into the compose area."""
        ta = self.query_one("#compose-input", TextArea)
        quoted = "\n".join(f"> {line}" for line in text.splitlines())
        current = ta.text
        if current:
            ta.load_text(f"{current}\n{quoted}\n\n")
        else:
            ta.load_text(f"{quoted}\n\n")
        ta.focus()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the compose area."""
        ta = self.query_one("#compose-input", TextArea)
        btn = self.query_one("#send-btn", Button)
        ta.disabled = not enabled
        btn.disabled = not enabled
