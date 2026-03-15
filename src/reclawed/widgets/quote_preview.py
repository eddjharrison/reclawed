"""Reply/quote preview strip shown above the compose area."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message as TMessage
from textual.reactive import reactive
from textual.widgets import Button, Label, Static


class QuotePreview(Static):
    """Shows 'Replying to...' context above the compose area."""

    DEFAULT_CSS = """
    QuotePreview {
        width: 100%;
        height: auto;
        max-height: 3;
        display: none;
        background: $primary-background;
        padding: 0 1;
    }
    QuotePreview.visible {
        display: block;
    }
    QuotePreview .quote-text {
        color: $text-muted;
        text-style: italic;
    }
    QuotePreview .quote-cancel {
        dock: right;
        min-width: 3;
        color: $error;
    }
    """

    reply_to_id: reactive[str | None] = reactive(None)

    class Cancelled(TMessage):
        """Posted when the user cancels the reply."""

    def compose(self) -> ComposeResult:
        yield Label("", id="quote-label", classes="quote-text")
        yield Button("x", id="quote-cancel", classes="quote-cancel", variant="error")

    def show_reply(self, message_id: str, preview_text: str) -> None:
        self.reply_to_id = message_id
        label = self.query_one("#quote-label", Label)
        label.update(f"Replying to: {preview_text[:120]}")
        self.add_class("visible")

    def hide(self) -> None:
        self.reply_to_id = None
        self.remove_class("visible")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quote-cancel":
            self.hide()
            self.post_message(self.Cancelled())
