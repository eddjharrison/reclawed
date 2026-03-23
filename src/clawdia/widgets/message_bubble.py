"""Single message bubble widget with markdown rendering."""

from __future__ import annotations

import re
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Click
from textual.message import Message as TMessage
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import Label, Markdown, Static

_THINKING_FRAMES = [".  ", ".. ", "...", " ..", "  .", "   "]

from reclawed.models import Message
from reclawed.utils import (
    detect_choices, detect_question, format_file_size, format_relative_time,
    parse_attachments,
)
from reclawed.widgets.choice_buttons import ChoiceButtons
from reclawed.widgets.tool_activity import ToolActivityWidget

# File extensions to detect as clickable file paths
_FILE_EXT = (
    r'\.(?:py|md|toml|json|ts|js|jsx|tsx|css|html|htm|yml|yaml|sh|bash|zsh'
    r'|txt|cfg|ini|sql|rs|go|rb|java|cpp|c|h|cs|php|swift|kt|dart'
    r'|ex|exs|lua|r|m|scala|clj|hs|ml|fs|elm|nim|zig|v|cr|jl|tf|hcl'
    r'|proto|graphql|gql|lock|env|vue|svelte|astro|mdx|rst|log)'
)

# Patterns — ordered by confidence
_BACKTICK_PATH_RE = re.compile(
    r'`([^`\n]+' + _FILE_EXT + r'[^`\n]*)`'
)
_ABSOLUTE_PATH_RE = re.compile(
    r'(?<!["\'\w])((?:/[a-zA-Z0-9_.\-@]+)+' + _FILE_EXT + r'(?:/[a-zA-Z0-9_.\-@]*)*)'
)
_RELATIVE_PATH_RE = re.compile(
    r'(?<!["\'\w:/])'               # not preceded by quote, word, colon, or slash
    r'([a-zA-Z0-9_.\-]+(?:/[a-zA-Z0-9_.\-]+)+' + _FILE_EXT + r')'
    r'(?!["\'\w])'                  # not followed by quote or word char
)

# Code-fence block pattern — skip anything between ``` fences
_CODE_FENCE_RE = re.compile(r'```.*?```', re.DOTALL)
# Inline code — also skip single-backtick sections (we handle those separately)
_INLINE_CODE_RE = re.compile(r'`[^`]+`')
# URL pattern — skip file-like tokens that are actually URLs
_URL_RE = re.compile(r'https?://')


def extract_file_paths(content: str) -> list[str]:
    """Extract unique file paths from message content.

    Skips code-fence blocks, URLs, and duplicate paths.
    Returns paths in order of first appearance.
    """
    # Remove code-fence blocks before scanning
    cleaned = _CODE_FENCE_RE.sub('', content)

    seen: set[str] = set()
    paths: list[str] = []

    def _add(path: str) -> None:
        path = path.strip()
        if path and path not in seen and not _URL_RE.search(path):
            seen.add(path)
            paths.append(path)

    # 1. Backtick-wrapped paths (high confidence)
    for m in _BACKTICK_PATH_RE.finditer(cleaned):
        _add(m.group(1))

    # 2. Absolute paths (high confidence) — scan cleaned text (no fences)
    no_inline = _INLINE_CODE_RE.sub('', cleaned)
    for m in _ABSOLUTE_PATH_RE.finditer(no_inline):
        _add(m.group(1))

    # 3. Relative paths with at least one directory component
    for m in _RELATIVE_PATH_RE.finditer(no_inline):
        _add(m.group(1))

    return paths


class ClickableFileChip(Label):
    """A small clickable chip showing a file path detected in message content."""

    DEFAULT_CSS = """
    ClickableFileChip {
        color: $accent;
        text-style: underline;
        margin: 0 1 0 0;
    }
    ClickableFileChip:hover {
        background: $accent 20%;
    }
    """

    def __init__(self, path: str, **kwargs) -> None:
        # Show shortened display name — last 2 path components at most
        from pathlib import PurePosixPath
        parts = PurePosixPath(path).parts
        display = "/".join(parts[-2:]) if len(parts) > 2 else path
        super().__init__(f"📄 {display}", **kwargs)
        self._path = path

    def on_click(self, event: Click) -> None:
        event.stop()
        self.post_message(MessageBubble.FileClicked(self._path))


class ReplyIndicator(Label):
    """Clickable reply-quote banner that navigates back to the original message."""

    def __init__(self, text: str, reply_to_id: str, **kwargs) -> None:
        super().__init__(text, **kwargs)
        self._reply_to_id = reply_to_id

    def on_click(self, event: Click) -> None:
        # Stop propagation so the parent MessageBubble.on_click is not also fired.
        event.stop()
        self.post_message(MessageBubble.ReplyClicked(self._reply_to_id))


class AttachmentIndicator(Label):
    """Clickable attachment label in message bubbles — click to preview."""

    def __init__(self, text: str, file_path: str, **kwargs) -> None:
        super().__init__(text, **kwargs)
        self._file_path = file_path

    def on_click(self, event: Click) -> None:
        event.stop()
        self.post_message(MessageBubble.AttachmentPreviewRequested(self._file_path))


class MessageBubble(Vertical):
    """Displays a single chat message with role styling and optional reply indicator."""

    DEFAULT_CSS = """
    MessageBubble {
        width: 100%;
        height: auto;
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
    MessageBubble .bubble-header.sender-human {
        color: $success;
    }
    MessageBubble .bubble-header.sender-claude {
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
    MessageBubble .pin-indicator {
        color: $warning;
        text-style: bold;
        margin-bottom: 0;
    }
    MessageBubble .bubble-meta {
        color: $text-disabled;
        text-style: dim;
    }
    MessageBubble .edited-indicator {
        color: $text-disabled;
        text-style: italic dim;
    }
    MessageBubble .delivery-status {
        color: $text-disabled;
        text-style: dim;
    }
    MessageBubble .delivery-status.read {
        color: $accent;
    }
    MessageBubble.deleted .bubble-header {
        color: $text-disabled;
    }
    MessageBubble.has-question {
        border-left: thick $warning;
    }
    MessageBubble .deleted-placeholder {
        color: $text-disabled;
        text-style: italic dim;
    }
    MessageBubble .attachment-indicator {
        color: $accent;
        background: $primary 10%;
        padding: 0 1;
        margin-bottom: 0;
        border-left: thick $accent;
    }
    MessageBubble .attachment-indicator:hover {
        text-style: underline;
        background: $primary 20%;
    }
    MessageBubble .file-chips-row {
        layout: horizontal;
        height: auto;
        padding: 0 0 0 0;
        margin-top: 0;
    }
    """

    selected: reactive[bool] = reactive(False)

    class Selected(TMessage):
        """Posted when this bubble is clicked/selected."""
        def __init__(self, message_id: str) -> None:
            super().__init__()
            self.message_id = message_id

    class AttachmentPreviewRequested(TMessage):
        """Posted when user clicks an attachment indicator to preview it."""
        def __init__(self, path: str) -> None:
            super().__init__()
            self.path = path

    class ReplyClicked(TMessage):
        """Posted when the reply-indicator banner is clicked.

        ``reply_to_id`` is the ID of the original message that should be
        scrolled into view and selected.
        """
        def __init__(self, reply_to_id: str) -> None:
            super().__init__()
            self.reply_to_id = reply_to_id

    class FileClicked(TMessage):
        """Posted when a file reference inside a message bubble is clicked.

        ``path`` is the absolute (or workspace-relative) path to the file.
        """
        def __init__(self, path: str) -> None:
            super().__init__()
            self.path = path

    def __init__(self, message: Message, reply_preview: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._message = message
        self._reply_preview = reply_preview
        self._content_widget: Markdown | None = None
        self._stream_widget: Static | None = None  # fast text display during streaming
        self._delivery_label: Label | None = None
        self._thinking_timer: Timer | None = None
        self._thinking_frame: int = 0
        self.add_class(message.role)

    @property
    def message(self) -> Message:
        return self._message

    @property
    def message_id(self) -> str:
        return self._message.id

    def compose(self) -> ComposeResult:
        # If the message carries an explicit sender_name (group chat), use it.
        # Otherwise fall back to the generic "You" / "Claude" role labels.
        if self._message.sender_name:
            role_label = self._message.sender_name
        else:
            role_label = "You" if self._message.role == "user" else "Claude"

        ts = format_relative_time(self._message.timestamp)

        # Deleted messages show only a placeholder
        if self._message.deleted:
            self.add_class("deleted")
            yield Label(f"{role_label}  {ts}", classes="bubble-header")
            yield Label("[This message was deleted]", classes="deleted-placeholder")
            return

        if self._message.bookmarked:
            yield Label("# Pinned", classes="pin-indicator")

        if self._reply_preview and self._message.reply_to_id:
            preview_text = self._reply_preview[:80].replace("\n", " ")
            yield ReplyIndicator(
                f">> {preview_text}",
                reply_to_id=self._message.reply_to_id,
                classes="reply-indicator",
            )

        # Build CSS classes for the header — add sender_type class when present
        # so group chat messages get colour-coded regardless of the role field.
        header_classes = "bubble-header"
        if self._message.sender_type == "human":
            header_classes += " sender-human"
        elif self._message.sender_type == "claude":
            header_classes += " sender-claude"

        yield Label(f"{role_label}  {ts}", classes=header_classes)

        # Show attachment indicators if message has images (clickable to preview)
        attachments = parse_attachments(self._message.attachments)
        for att in attachments:
            filename = att.get("filename", "image")
            size = att.get("size_bytes", 0)
            file_path = att.get("path", "")
            size_str = format_file_size(size) if size else ""
            yield AttachmentIndicator(
                f"📁 {filename} ({size_str}) — click to preview",
                file_path=file_path,
                classes="attachment-indicator",
            )

        # Static widget for fast streaming display (hidden until streaming starts)
        self._stream_widget = Static("", id="bubble-stream", classes="bubble-stream")
        self._stream_widget.display = False
        yield self._stream_widget

        # Markdown widget for final rendered display
        self._content_widget = Markdown(self._message.content, id="bubble-content")
        yield self._content_widget

        if self._message.edited_at:
            yield Label("[edited]", classes="edited-indicator")

        if self._message.role == "assistant" and self._message.model:
            tokens = ""
            if self._message.input_tokens and self._message.output_tokens:
                tokens = f" | {self._message.input_tokens}+{self._message.output_tokens} tokens"
            cost = ""
            if self._message.cost_usd:
                cost = f" | ${self._message.cost_usd:.4f}"
            yield Label(f"{self._message.model}{tokens}{cost}", classes="bubble-meta")

        # Delivery status for outgoing messages in group chat
        if self._message.role == "user" and self._message.sender_type == "human":
            self._delivery_label = Label("", classes="delivery-status", id="delivery-status")
            yield self._delivery_label

    def on_mount(self) -> None:
        """Start thinking animation if this is a placeholder bubble."""
        if self._message.content == "..." and self._message.role == "assistant":
            self._start_thinking()

    def _start_thinking(self) -> None:
        if self._thinking_timer is None:
            self._thinking_frame = 0
            if self._content_widget is not None:
                self._content_widget.display = False
            if self._stream_widget is not None:
                self._stream_widget.display = True
                self._stream_widget.update(_THINKING_FRAMES[0])
            self._thinking_timer = self.set_interval(0.3, self._advance_thinking)

    def _advance_thinking(self) -> None:
        self._thinking_frame = (self._thinking_frame + 1) % len(_THINKING_FRAMES)
        if self._stream_widget is not None:
            self._stream_widget.update(_THINKING_FRAMES[self._thinking_frame])

    def _stop_thinking(self) -> None:
        if self._thinking_timer is not None:
            self._thinking_timer.stop()
            self._thinking_timer = None

    def update_content(self, content: str) -> None:
        """Update the message content during streaming.

        Shows a fast Static widget and hides Markdown during streaming.
        No widget mounting/removal — just show/hide + text update.
        Call ``finalize_content()`` when streaming ends to render as Markdown.
        """
        self._stop_thinking()
        self._message.content = content
        # Show the fast Static, hide the slow Markdown
        if self._stream_widget is not None:
            self._stream_widget.display = True
            self._stream_widget.update(content)
        if self._content_widget is not None:
            self._content_widget.display = False

    async def finalize_content(
        self,
        content: str,
        session_type: str | None = None,
        template_names: dict[str, str] | None = None,
        permission_mode: str | None = None,
    ) -> None:
        """Switch from streaming Static back to Markdown for final render."""
        self._stop_thinking()
        self._message.content = content
        # Hide streaming widget, show Markdown with final content
        if self._stream_widget is not None:
            self._stream_widget.display = False
        if self._content_widget is not None:
            self._content_widget.display = True
            await self._content_widget.update(content)

        # Mount clickable file chips for any file paths detected in content
        paths = extract_file_paths(content)
        if paths:
            # Remove any existing chips row to avoid duplicates on re-render
            for old in self.query(".file-chips-row"):
                await old.remove()
            chips = [ClickableFileChip(p) for p in paths]
            try:
                await self.mount(Horizontal(*chips, classes="file-chips-row"))
            except Exception:
                pass

        # Detect and display interactive elements
        if self._message.role == "assistant":
            if detect_question(content):
                self.add_class("has-question")

            # Skip ChoiceButtons if AskUserQuestionWidget is already mounted
            from reclawed.widgets.ask_user_question import AskUserQuestionWidget
            has_auq = bool(self.query(AskUserQuestionWidget))
            if not has_auq:
                choices = detect_choices(content)
                if choices:
                    try:
                        await self.mount(ChoiceButtons(choices))
                    except Exception:
                        pass

            # Detect worker spawn proposals (orchestrator sessions only)
            # Skip widget when bypassPermissions — auto-spawn handles it
            if session_type == "orchestrator" and permission_mode != "bypassPermissions":
                from reclawed.utils import detect_worker_proposals
                from reclawed.widgets.spawn_proposals import SpawnProposalsWidget
                proposals = detect_worker_proposals(content)
                if proposals:
                    try:
                        await self.mount(SpawnProposalsWidget(
                            proposals,
                            self._message.session_id,
                            template_names=template_names,
                        ))
                    except Exception:
                        pass

    def add_tool_use(self, tool_use_id: str, tool_name: str, tool_input: dict) -> None:
        """Mount a tool activity widget showing an in-progress tool call."""
        widget = ToolActivityWidget(tool_use_id, tool_name, tool_input)
        # Mount before the content widget so tools appear above the text
        try:
            if self._content_widget is not None:
                self.mount(widget, before=self._content_widget)
            else:
                self.mount(widget)
        except Exception:
            pass

    def complete_tool(self, tool_use_id: str, content: str | None, is_error: bool) -> None:
        """Mark a tool as completed with its result."""
        for widget in self.query(ToolActivityWidget):
            if widget.tool_use_id == tool_use_id:
                widget.complete(content, is_error)
                break

    async def mark_deleted(self) -> None:
        """Transition this bubble to the deleted state in-place."""
        self._message.deleted = True
        self.add_class("deleted")
        # Replace content with placeholder
        await self.remove_children()
        role_label = self._message.sender_name or ("You" if self._message.role == "user" else "Claude")
        ts = format_relative_time(self._message.timestamp)
        await self.mount(Label(f"{role_label}  {ts}", classes="bubble-header"))
        await self.mount(Label("[This message was deleted]", classes="deleted-placeholder"))

    def set_delivery_status(self, status: str) -> None:
        """Update delivery status indicator. status: 'sent', 'delivered', or 'read'."""
        if self._delivery_label is None:
            try:
                self._delivery_label = self.query_one("#delivery-status", Label)
            except Exception:
                return
        symbols = {"sent": "\u2713", "delivered": "\u2713\u2713", "read": "\u2713\u2713"}
        self._delivery_label.update(symbols.get(status, ""))
        if status == "read":
            self._delivery_label.add_class("read")
        else:
            self._delivery_label.remove_class("read")

    def watch_selected(self, value: bool) -> None:
        if value:
            self.add_class("selected")
        else:
            self.remove_class("selected")

    def on_click(self) -> None:
        self.post_message(self.Selected(self._message.id))
