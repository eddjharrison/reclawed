"""Inline widget showing tool activity within a message bubble."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Click
from textual.message import Message as TMessage
from textual.widgets import Label

# Tool names that operate on a single file path via the ``file_path`` input key.
_FILE_TOOLS = {"Read", "Edit", "MultiEdit", "Write"}


def _tool_summary(tool_name: str, tool_input: dict) -> str:
    """Generate a human-readable one-line summary of a tool invocation."""
    if tool_name == "Read":
        return f"Reading {tool_input.get('file_path', '...')}"
    elif tool_name in ("Edit", "MultiEdit"):
        return f"Editing {tool_input.get('file_path', '...')}"
    elif tool_name == "Write":
        return f"Writing {tool_input.get('file_path', '...')}"
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "...")
        if len(cmd) > 60:
            cmd = cmd[:57] + "..."
        return f"Running: {cmd}"
    elif tool_name == "Grep":
        return f"Searching for '{tool_input.get('pattern', '...')}'"
    elif tool_name == "Glob":
        return f"Finding {tool_input.get('pattern', '...')}"
    elif tool_name == "WebFetch":
        return f"Fetching {tool_input.get('url', '...')}"
    elif tool_name == "WebSearch":
        return f"Searching: {tool_input.get('query', '...')}"
    else:
        return f"Using {tool_name}"


def _file_path_for_tool(tool_name: str, tool_input: dict) -> str | None:
    """Return the primary file path for a file-based tool, or None."""
    if tool_name in _FILE_TOOLS:
        return tool_input.get("file_path") or None
    return None


class ToolActivityWidget(Vertical):
    """Displays a tool invocation inline within a message bubble.

    Shows a human-readable summary header and a collapsible detail section
    with the tool input and result.

    Clicking the header of a completed file-based tool (Read / Edit / Write)
    posts a ``FileClicked`` message so the chat screen can open the file in
    ``DocumentScreen``.  Clicking anywhere else on the widget toggles the
    detail panel.
    """

    DEFAULT_CSS = """
    ToolActivityWidget {
        width: 100%;
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
        border-left: thick $primary 40%;
        background: $surface;
    }
    ToolActivityWidget .tool-header {
        width: 100%;
        color: $text-muted;
    }
    ToolActivityWidget .tool-header:hover {
        color: $accent;
    }
    ToolActivityWidget.tool-complete .tool-header {
        color: $success;
    }
    ToolActivityWidget.tool-file .tool-header:hover {
        text-style: underline;
        cursor: pointer;
    }
    ToolActivityWidget.tool-error .tool-header {
        color: $error;
    }
    ToolActivityWidget .tool-detail {
        width: 100%;
        color: $text-muted;
        display: none;
        padding: 0 1;
    }
    ToolActivityWidget.expanded .tool-detail {
        display: block;
    }
    """

    class FileClicked(TMessage):
        """Posted when the user clicks the header of a completed file-based tool.

        The receiver (``ChatScreen``) should open the file in ``DocumentScreen``.
        """
        def __init__(self, path: str) -> None:
            super().__init__()
            self.path = path

    def __init__(self, tool_use_id: str, tool_name: str, tool_input: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tool_use_id = tool_use_id
        self._tool_name = tool_name
        self._tool_input = tool_input
        self._result_content: str | None = None
        self._is_error = False
        self._file_path: str | None = _file_path_for_tool(tool_name, tool_input)

    @property
    def tool_use_id(self) -> str:
        return self._tool_use_id

    def compose(self) -> ComposeResult:
        summary = _tool_summary(self._tool_name, self._tool_input)
        yield Label(f"... {summary}", classes="tool-header")
        yield Label("", classes="tool-detail")

    def complete(self, content: str | None, is_error: bool) -> None:
        """Mark the tool as completed with a result."""
        self._result_content = content
        self._is_error = is_error

        summary = _tool_summary(self._tool_name, self._tool_input)
        prefix = "x" if is_error else "+"

        # For successful file tools, append a subtle hint that the path is clickable
        hint = " 📄" if (self._file_path and not is_error) else ""
        try:
            header = self.query_one(".tool-header", Label)
            header.update(f"[{prefix}] {summary}{hint}")
        except Exception:
            pass

        if is_error:
            self.add_class("tool-error")
        else:
            self.add_class("tool-complete")
            if self._file_path:
                self.add_class("tool-file")

        # Populate detail with truncated result
        if content:
            detail_text = content
            if len(detail_text) > 500:
                detail_text = detail_text[:497] + "..."
            try:
                detail = self.query_one(".tool-detail", Label)
                detail.update(detail_text)
            except Exception:
                pass

    def on_click(self, event: Click) -> None:
        """Handle clicks:

        * If the tool is a completed file tool and the header was clicked,
          post ``FileClicked`` so the chat screen opens the file.
        * Otherwise toggle the detail panel.
        """
        event.stop()

        # Check whether the click landed on the tool-header label.
        clicked_header = False
        try:
            header = self.query_one(".tool-header", Label)
            # Label occupies the full width; compare Y offset within the widget.
            # Textual gives us event.offset relative to the *widget* that received
            # the event (this Vertical).  The header is the first child, so it
            # starts at y=0 and is exactly 1 row tall.
            clicked_header = (event.offset.y == 0)
        except Exception:
            pass

        if clicked_header and self._file_path and self.has_class("tool-complete") and not self._is_error:
            self.post_message(self.FileClicked(self._file_path))
        else:
            self.toggle_class("expanded")
