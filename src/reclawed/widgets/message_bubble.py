"""Single message bubble widget with markdown rendering."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message as TMessage
from textual.reactive import reactive
from textual.widgets import Label, Markdown, Static

from reclawed.models import Message


class MessageBubble(Vertical):
    """Displays a single chat message with role styling and optional reply indicator."""

    DEFAULT_CSS = """
    MessageBubble {
        width: 100%;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    MessageBubble.user {
        background: $primary-background;
    }
    MessageBubble.assistant {
        background: $surface;
    }
    MessageBubble.selected {
        border: tall $accent;
    }
    MessageBubble .bubble-header {
        color: $text-muted;
        text-style: bold;
        margin-bottom: 0;
    }
    MessageBubble.user .bubble-header {
        color: $success;
    }
    MessageBubble.assistant .bubble-header {
        color: $primary;
    }
    MessageBubble .reply-indicator {
        color: $accent;
        text-style: italic;
        background: $primary 10%;
        padding: 0 1;
        margin-bottom: 0;
        border-left: thick $accent;
    }
    MessageBubble .bubble-meta {
        color: $text-disabled;
        text-style: dim;
    }
    """

    selected: reactive[bool] = reactive(False)

    class Selected(TMessage):
        """Posted when this bubble is clicked/selected."""
        def __init__(self, message_id: str) -> None:
            super().__init__()
            self.message_id = message_id

    def __init__(self, message: Message, reply_preview: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._message = message
        self._reply_preview = reply_preview
        self._content_widget: Markdown | None = None
        self.add_class(message.role)

    @property
    def message(self) -> Message:
        return self._message

    @property
    def message_id(self) -> str:
        return self._message.id

    def compose(self) -> ComposeResult:
        role_label = "You" if self._message.role == "user" else "Claude"
        ts = self._message.timestamp.strftime("%H:%M")
        bookmark = " *" if self._message.bookmarked else ""

        if self._reply_preview:
            preview_text = self._reply_preview[:80].replace("\n", " ")
            yield Label(f">> {preview_text}", classes="reply-indicator")

        yield Label(f"{role_label}  {ts}{bookmark}", classes="bubble-header")

        self._content_widget = Markdown(self._message.content, id="bubble-content")
        yield self._content_widget

        if self._message.role == "assistant" and self._message.model:
            tokens = ""
            if self._message.input_tokens and self._message.output_tokens:
                tokens = f" | {self._message.input_tokens}+{self._message.output_tokens} tokens"
            cost = ""
            if self._message.cost_usd:
                cost = f" | ${self._message.cost_usd:.4f}"
            yield Label(f"{self._message.model}{tokens}{cost}", classes="bubble-meta")

    def update_content(self, content: str) -> None:
        """Update the message content (used during streaming)."""
        self._message.content = content
        if self._content_widget:
            self._content_widget.update(content)

    def watch_selected(self, value: bool) -> None:
        if value:
            self.add_class("selected")
        else:
            self.remove_class("selected")

    def on_click(self) -> None:
        self.post_message(self.Selected(self._message.id))
