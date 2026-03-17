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

    class MentionRequested(TMessage):
        """Posted when user types @ to trigger mention autocomplete."""

    def _on_key(self, event: Key) -> None:
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.post_message(self.SendRequested())
        elif event.key in ("shift+enter", "shift+return", "ctrl+j"):
            # ctrl+j is what Windows Terminal sends for Ctrl+Enter
            event.prevent_default()
            event.stop()
            self.insert("\n")
        elif event.key == "ctrl+delete":
            # Delete word forward
            event.prevent_default()
            event.stop()
            self.action_delete_word_right()
        elif event.key == "ctrl+shift+delete":
            # Clear entire input
            event.prevent_default()
            event.stop()
            self.clear()
        elif event.key == "at":
            # Let the @ character be inserted, then request mention autocomplete
            self.call_later(lambda: self.post_message(self.MentionRequested()))


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
        def __init__(self, text: str, editing_message_id: str | None = None) -> None:
            super().__init__()
            self.text = text
            self.editing_message_id = editing_message_id

    class TypingStarted(TMessage):
        """Posted when the user types in the compose area."""

    class MentionTriggered(TMessage):
        """Posted when @mention autocomplete is needed."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._editing_message_id: str | None = None
        self._participants: list[str] = []  # participant names for @mention

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

    def on_text_area_changed(self, event) -> None:
        """Post TypingStarted on any text change."""
        self.post_message(self.TypingStarted())

    def on_compose_input_mention_requested(self, event: ComposeInput.MentionRequested) -> None:
        """Forward mention request to ChatScreen."""
        event.stop()
        if self._participants:
            self.post_message(self.MentionTriggered())

    def set_participants(self, names: list[str]) -> None:
        """Set the list of participant names for @mention autocomplete."""
        self._participants = names

    def insert_mention(self, name: str) -> None:
        """Insert a @mention at the current cursor position."""
        ta = self.query_one("#compose-input", ComposeInput)
        ta.insert(f"{name} ")
        ta.focus()

    def _submit(self) -> None:
        ta = self.query_one("#compose-input", ComposeInput)
        text = ta.text.strip()
        if text:
            self.post_message(self.Submitted(text, editing_message_id=self._editing_message_id))
            ta.clear()
            self._editing_message_id = None
            # Remove edit indicator if present
            try:
                self.query_one("#edit-indicator").remove()
            except Exception:
                pass

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

    def start_edit(self, message_id: str, content: str) -> None:
        """Enter edit mode: pre-fill with content and show indicator."""
        from textual.widgets import Label
        self._editing_message_id = message_id
        ta = self.query_one("#compose-input", ComposeInput)
        ta.load_text(content)
        ta.focus()
        # Add edit indicator above compose if not already present
        try:
            self.query_one("#edit-indicator")
        except Exception:
            indicator = Label("[Editing...] Press Escape to cancel", id="edit-indicator")
            self.mount(indicator, before=ta)

    def cancel_edit(self) -> None:
        """Cancel edit mode and clear the compose area."""
        self._editing_message_id = None
        ta = self.query_one("#compose-input", ComposeInput)
        ta.clear()
        try:
            self.query_one("#edit-indicator").remove()
        except Exception:
            pass

    def action_cancel(self) -> None:
        """Handle Escape — cancel edit mode if active, otherwise no-op."""
        if self._editing_message_id is not None:
            self.cancel_edit()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the compose area."""
        ta = self.query_one("#compose-input", ComposeInput)
        btn = self.query_one("#send-btn", Button)
        ta.disabled = not enabled
        btn.disabled = not enabled
