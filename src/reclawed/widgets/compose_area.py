"""Compose area with text input, send functionality, and image attachments."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.message import Message as TMessage
from textual.widgets import Button, TextArea

from reclawed.widgets.attachment_preview import AttachmentPreview


class ComposeInput(TextArea):
    """TextArea that sends on Enter and inserts newline on Shift+Enter."""

    class SendRequested(TMessage):
        """Posted when user presses Enter (without modifiers)."""

    class MentionRequested(TMessage):
        """Posted when user types @ to trigger mention autocomplete."""

    class PasteImageRequested(TMessage):
        """Posted when user presses Alt+V to paste an image from clipboard."""

    class AttachFileRequested(TMessage):
        """Posted when user presses Alt+A to attach a file by path."""

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
        elif event.key == "alt+v":
            # Paste image from clipboard
            event.prevent_default()
            event.stop()
            self.post_message(self.PasteImageRequested())
        elif event.key == "alt+a":
            # Attach file by path
            event.prevent_default()
            event.stop()
            self.post_message(self.AttachFileRequested())


class ComposeArea(Vertical):
    """Text input area with send button and attachment support."""

    DEFAULT_CSS = """
    ComposeArea {
        width: 100%;
        height: auto;
        min-height: 3;
        max-height: 14;
        dock: bottom;
        padding: 0 1;
    }
    ComposeArea #compose-row {
        width: 100%;
        height: auto;
        min-height: 3;
        max-height: 10;
    }
    ComposeArea ComposeInput {
        width: 1fr;
        min-height: 3;
        max-height: 8;
    }
    ComposeArea #button-col {
        width: 10;
        height: auto;
        margin-left: 1;
    }
    ComposeArea #send-btn {
        width: 100%;
        min-height: 3;
    }
    ComposeArea #attach-btn {
        width: 100%;
        height: 1;
        min-height: 1;
        background: $surface;
        color: $text-muted;
        border: none;
    }
    ComposeArea #attach-btn:hover {
        background: $primary 30%;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    class Submitted(TMessage):
        """Posted when the user submits a message."""
        def __init__(
            self,
            text: str,
            editing_message_id: str | None = None,
            attachments: list[str] | None = None,
        ) -> None:
            super().__init__()
            self.text = text
            self.editing_message_id = editing_message_id
            self.attachments = attachments or []

    class TypingStarted(TMessage):
        """Posted when the user types in the compose area."""

    class MentionTriggered(TMessage):
        """Posted when @mention autocomplete is needed."""

    class AttachFileTriggered(TMessage):
        """Posted when the user wants to attach a file (opens path input)."""

    class PasteImageTriggered(TMessage):
        """Posted when the user wants to paste an image from clipboard."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._editing_message_id: str | None = None
        self._participants: list[str] = []  # participant names for @mention

    def compose(self) -> ComposeResult:
        yield AttachmentPreview(id="attachment-preview")
        with Horizontal(id="compose-row"):
            yield ComposeInput(id="compose-input")
            with Vertical(id="button-col"):
                yield Button("Send", id="send-btn", variant="primary")
                yield Button("📁 Attach", id="attach-btn", variant="default")

    def on_mount(self) -> None:
        self.query_one("#compose-input", ComposeInput).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            self._submit()
        elif event.button.id == "attach-btn":
            event.stop()
            self.post_message(self.AttachFileTriggered())

    def on_compose_input_send_requested(self) -> None:
        self._submit()

    def on_compose_input_paste_image_requested(self, event: ComposeInput.PasteImageRequested) -> None:
        """Forward paste request to ChatScreen."""
        event.stop()
        self.post_message(self.PasteImageTriggered())

    def on_compose_input_attach_file_requested(self, event: ComposeInput.AttachFileRequested) -> None:
        """Forward attach request to ChatScreen."""
        event.stop()
        self.post_message(self.AttachFileTriggered())

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

    def add_attachment(self, path: str) -> None:
        """Add an image attachment to the preview strip."""
        preview = self.query_one("#attachment-preview", AttachmentPreview)
        preview.add_attachment(path)

    def get_attachments(self) -> list[str]:
        """Return current attachment file paths."""
        preview = self.query_one("#attachment-preview", AttachmentPreview)
        return preview.paths

    def clear_attachments(self) -> None:
        """Remove all queued attachments."""
        preview = self.query_one("#attachment-preview", AttachmentPreview)
        preview.clear()

    def _submit(self) -> None:
        ta = self.query_one("#compose-input", ComposeInput)
        text = ta.text.strip()
        attachments = self.get_attachments()
        if text or attachments:
            self.post_message(self.Submitted(
                text or "(image attached)",
                editing_message_id=self._editing_message_id,
                attachments=attachments,
            ))
            ta.clear()
            self.clear_attachments()
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
        self.clear_attachments()
        try:
            self.query_one("#edit-indicator").remove()
        except Exception:
            pass

    def action_cancel(self) -> None:
        """Handle Escape — cancel edit mode if active, otherwise clear attachments."""
        if self._editing_message_id is not None:
            self.cancel_edit()
        elif self.get_attachments():
            self.clear_attachments()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the compose area."""
        ta = self.query_one("#compose-input", ComposeInput)
        btn = self.query_one("#send-btn", Button)
        ta.disabled = not enabled
        btn.disabled = not enabled
