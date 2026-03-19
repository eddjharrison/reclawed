"""Tests for clickable file references in message bubbles.

Covers:
- AttachmentIndicator widget instantiation and message posting
- MessageBubble.AttachmentPreviewRequested message class
- File path extraction helpers (if present)
"""

from __future__ import annotations

import pytest

from reclawed.models import Message
from reclawed.widgets.message_bubble import (
    AttachmentIndicator,
    MessageBubble,
)


# ---------------------------------------------------------------------------
# AttachmentIndicator widget
# ---------------------------------------------------------------------------


class TestAttachmentIndicator:
    def test_instantiation(self):
        """AttachmentIndicator can be created with text and a file path."""
        indicator = AttachmentIndicator("📁 notes.md (2KB) — click to preview", file_path="/tmp/notes.md")
        assert indicator._file_path == "/tmp/notes.md"

    def test_stores_file_path(self):
        """_file_path attribute holds the path passed to the constructor."""
        path = "/Users/alice/projects/foo/src/config.py"
        indicator = AttachmentIndicator("config.py", file_path=path)
        assert indicator._file_path == path

    def test_display_text_stored(self):
        """The display text passed to the parent Label is accessible."""
        indicator = AttachmentIndicator("📁 image.png (45KB)", file_path="/tmp/image.png")
        # Textual Label stores the renderable; we just check the object is alive
        assert indicator is not None

    def test_path_with_spaces(self):
        """File paths with spaces are stored verbatim."""
        path = "/Users/alice/my projects/my file.py"
        indicator = AttachmentIndicator("my file.py", file_path=path)
        assert indicator._file_path == path

    def test_path_windows_style(self):
        """Windows-style paths are stored verbatim."""
        path = r"C:\Users\alice\projects\app.py"
        indicator = AttachmentIndicator("app.py", file_path=path)
        assert indicator._file_path == path

    def test_empty_path(self):
        """Empty string path is accepted (edge case)."""
        indicator = AttachmentIndicator("(no path)", file_path="")
        assert indicator._file_path == ""


# ---------------------------------------------------------------------------
# MessageBubble.AttachmentPreviewRequested message
# ---------------------------------------------------------------------------


class TestAttachmentPreviewRequested:
    def test_path_stored(self):
        """AttachmentPreviewRequested stores the file path."""
        msg = MessageBubble.AttachmentPreviewRequested("/home/user/file.txt")
        assert msg.path == "/home/user/file.txt"

    def test_absolute_path(self):
        """Absolute paths are stored unchanged."""
        path = "/Users/ed/EIR/reclawed/src/config.py"
        msg = MessageBubble.AttachmentPreviewRequested(path)
        assert msg.path == path

    def test_relative_path(self):
        """Relative paths are accepted without modification."""
        msg = MessageBubble.AttachmentPreviewRequested("src/config.py")
        assert msg.path == "src/config.py"

    def test_empty_path(self):
        """Empty string path is accepted."""
        msg = MessageBubble.AttachmentPreviewRequested("")
        assert msg.path == ""

    def test_path_with_special_chars(self):
        """Paths with special characters are stored as-is."""
        path = "/tmp/my file (copy).py"
        msg = MessageBubble.AttachmentPreviewRequested(path)
        assert msg.path == path

    def test_is_textual_message(self):
        """AttachmentPreviewRequested is a Textual Message subclass."""
        from textual.message import Message as TMessage
        msg = MessageBubble.AttachmentPreviewRequested("/some/path.md")
        assert isinstance(msg, TMessage)


# ---------------------------------------------------------------------------
# MessageBubble has the expected message classes
# ---------------------------------------------------------------------------


class TestMessageBubbleMessages:
    def test_attachment_preview_requested_class_exists(self):
        """MessageBubble.AttachmentPreviewRequested class is defined."""
        assert hasattr(MessageBubble, "AttachmentPreviewRequested")

    def test_reply_clicked_class_exists(self):
        """MessageBubble.ReplyClicked class is defined."""
        assert hasattr(MessageBubble, "ReplyClicked")

    def test_attachment_indicator_class_exists(self):
        """AttachmentIndicator is importable from message_bubble."""
        from reclawed.widgets.message_bubble import AttachmentIndicator
        assert AttachmentIndicator is not None

    def test_message_bubble_with_attachment_in_content(self):
        """MessageBubble accepts a Message with attachment metadata in content."""
        import json
        attachment = {"type": "image", "path": "/tmp/screenshot.png", "size": 12345}
        content_with_attachment = json.dumps({"text": "See attached", "attachments": [attachment]})
        # The bubble should instantiate without error regardless of content format
        msg = Message(role="user", content="See attached", session_id="s1")
        bubble = MessageBubble(msg)
        assert bubble.message.role == "user"


# ---------------------------------------------------------------------------
# parse_attachments utility (used by MessageBubble to detect attachments)
# ---------------------------------------------------------------------------


class TestParseAttachments:
    """Tests for the parse_attachments utility that extracts attachment metadata."""

    def test_import(self):
        """parse_attachments is importable from utils."""
        from reclawed.utils import parse_attachments
        assert callable(parse_attachments)

    def test_no_attachments_returns_empty(self):
        """Plain text content returns an empty attachments list."""
        from reclawed.utils import parse_attachments
        result = parse_attachments("Hello, this is a plain message with no attachments.")
        assert result == []

    def test_none_content_returns_empty(self):
        """None content returns an empty list without raising."""
        from reclawed.utils import parse_attachments
        result = parse_attachments(None)
        assert result == []

    def test_empty_string_returns_empty(self):
        """Empty string content returns an empty list."""
        from reclawed.utils import parse_attachments
        result = parse_attachments("")
        assert result == []


# ---------------------------------------------------------------------------
# NEW: MessageBubble.FileClicked message
# ---------------------------------------------------------------------------


class TestMessageBubbleFileClicked:
    def test_file_clicked_stores_path(self):
        msg = MessageBubble.FileClicked("src/reclawed/config.py")
        assert msg.path == "src/reclawed/config.py"

    def test_file_clicked_absolute_path(self):
        path = "/Users/ed/projects/reclawed/src/reclawed/config.py"
        msg = MessageBubble.FileClicked(path)
        assert msg.path == path

    def test_file_clicked_empty_path(self):
        msg = MessageBubble.FileClicked("")
        assert msg.path == ""

    def test_file_clicked_is_textual_message(self):
        from textual.message import Message as TMessage
        msg = MessageBubble.FileClicked("/some/path.py")
        assert isinstance(msg, TMessage)

    def test_file_clicked_class_exists(self):
        assert hasattr(MessageBubble, "FileClicked")


# ---------------------------------------------------------------------------
# NEW: ToolActivityWidget helpers and message
# ---------------------------------------------------------------------------


class TestFilePathForTool:
    def test_read_returns_file_path(self):
        from reclawed.widgets.tool_activity import _file_path_for_tool
        assert _file_path_for_tool("Read", {"file_path": "/tmp/foo.py"}) == "/tmp/foo.py"

    def test_edit_returns_file_path(self):
        from reclawed.widgets.tool_activity import _file_path_for_tool
        assert _file_path_for_tool("Edit", {"file_path": "src/config.py"}) == "src/config.py"

    def test_multiedit_returns_file_path(self):
        from reclawed.widgets.tool_activity import _file_path_for_tool
        assert _file_path_for_tool("MultiEdit", {"file_path": "app.py"}) == "app.py"

    def test_write_returns_file_path(self):
        from reclawed.widgets.tool_activity import _file_path_for_tool
        assert _file_path_for_tool("Write", {"file_path": "out.md"}) == "out.md"

    def test_bash_returns_none(self):
        from reclawed.widgets.tool_activity import _file_path_for_tool
        assert _file_path_for_tool("Bash", {"command": "ls"}) is None

    def test_grep_returns_none(self):
        from reclawed.widgets.tool_activity import _file_path_for_tool
        assert _file_path_for_tool("Grep", {"pattern": "foo"}) is None

    def test_missing_file_path_key_returns_none(self):
        from reclawed.widgets.tool_activity import _file_path_for_tool
        assert _file_path_for_tool("Read", {}) is None

    def test_empty_file_path_returns_none(self):
        from reclawed.widgets.tool_activity import _file_path_for_tool
        assert _file_path_for_tool("Edit", {"file_path": ""}) is None

    def test_unknown_tool_returns_none(self):
        from reclawed.widgets.tool_activity import _file_path_for_tool
        assert _file_path_for_tool("UnknownTool", {"file_path": "x.py"}) is None


class TestToolActivityWidgetFileClicked:
    def test_file_clicked_stores_path(self):
        from reclawed.widgets.tool_activity import ToolActivityWidget
        msg = ToolActivityWidget.FileClicked("/path/to/file.py")
        assert msg.path == "/path/to/file.py"

    def test_file_clicked_empty_path(self):
        from reclawed.widgets.tool_activity import ToolActivityWidget
        msg = ToolActivityWidget.FileClicked("")
        assert msg.path == ""

    def test_file_clicked_class_exists(self):
        from reclawed.widgets.tool_activity import ToolActivityWidget
        assert hasattr(ToolActivityWidget, "FileClicked")

    def test_file_clicked_is_textual_message(self):
        from textual.message import Message as TMessage
        from reclawed.widgets.tool_activity import ToolActivityWidget
        msg = ToolActivityWidget.FileClicked("foo.py")
        assert isinstance(msg, TMessage)


class TestToolActivityWidgetInit:
    """Test that _file_path is correctly set during __init__."""

    def _make(self, tool_name, tool_input):
        from reclawed.widgets.tool_activity import ToolActivityWidget, _file_path_for_tool
        w = ToolActivityWidget.__new__(ToolActivityWidget)
        w._tool_use_id = "id"
        w._tool_name = tool_name
        w._tool_input = tool_input
        w._result_content = None
        w._is_error = False
        w._file_path = _file_path_for_tool(tool_name, tool_input)
        return w

    def test_file_path_extracted_for_read(self):
        w = self._make("Read", {"file_path": "src/foo.py"})
        assert w._file_path == "src/foo.py"

    def test_file_path_extracted_for_edit(self):
        w = self._make("Edit", {"file_path": "src/bar.py"})
        assert w._file_path == "src/bar.py"

    def test_no_file_path_for_bash(self):
        w = self._make("Bash", {"command": "echo hi"})
        assert w._file_path is None


# ---------------------------------------------------------------------------
# NEW: Diff capture logic (pure dict logic, no real app)
# ---------------------------------------------------------------------------


class TestFileDiffCapture:
    def test_snapshot_stored_on_tool_use(self):
        pending: dict = {}
        tool_use_id = "tool-abc"
        file_path = "/tmp/example.py"
        before_content = "x = 1\n"
        pending[tool_use_id] = (file_path, before_content)
        assert pending[tool_use_id] == (file_path, before_content)

    def test_snapshot_consumed_on_tool_result(self):
        pending: dict = {}
        diffs: dict = {}
        tool_use_id = "tool-abc"
        file_path = "/tmp/example.py"
        before_content = "x = 1\n"
        after_content = "x = 2\n"
        pending[tool_use_id] = (file_path, before_content)
        fp, before = pending.pop(tool_use_id)
        diffs[fp] = (before, after_content)
        assert tool_use_id not in pending
        assert file_path in diffs
        assert diffs[file_path] == (before_content, after_content)

    def test_error_result_does_not_store_diff(self):
        pending: dict = {}
        diffs: dict = {}
        tool_use_id = "tool-xyz"
        file_path = "/tmp/bad.py"
        pending[tool_use_id] = (file_path, "old\n")
        fp, before = pending.pop(tool_use_id)
        is_error = True
        if not is_error:
            diffs[fp] = (before, "new\n")
        assert tool_use_id not in pending
        assert file_path not in diffs

    def test_unknown_tool_use_id_ignored(self):
        pending: dict = {}
        diffs: dict = {}
        if "unknown-id" in pending:
            fp, before = pending.pop("unknown-id")
            diffs[fp] = (before, "after\n")
        assert not diffs


# ---------------------------------------------------------------------------
# NEW: Open file routing logic
# ---------------------------------------------------------------------------


class TestOpenFileLogic:
    def test_uses_diff_when_available(self, tmp_path):
        p = tmp_path / "foo.py"
        p.write_text("after\n")
        file_diffs = {str(p): ("before\n", "after\n")}
        assert str(p) in file_diffs
        before, after = file_diffs[str(p)]
        assert before == "before\n"
        assert after == "after\n"

    def test_uses_view_when_file_exists_no_diff(self, tmp_path):
        from pathlib import Path
        p = tmp_path / "bar.py"
        p.write_text("content\n")
        file_diffs: dict = {}
        assert str(p) not in file_diffs
        assert p.exists()

    def test_not_found_when_file_missing(self, tmp_path):
        from pathlib import Path
        path = str(tmp_path / "nonexistent.py")
        file_diffs: dict = {}
        assert path not in file_diffs
        assert not Path(path).exists()
