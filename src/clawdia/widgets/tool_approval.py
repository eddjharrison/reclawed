"""Inline tool approval widget — approve/deny buttons for tool calls."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message as TMessage
from textual.widgets import Button, Label

from clawdia.widgets.tool_activity import _tool_summary


class ToolApprovalWidget(Vertical):
    """Inline approve/deny prompt for a tool call.

    Posts ``ToolApprovalWidget.Decided(tool_use_id, approved)`` when the
    user clicks a button.
    """

    DEFAULT_CSS = """
    ToolApprovalWidget {
        width: 100%;
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
        border-left: thick $warning;
        background: $surface;
    }
    ToolApprovalWidget .approval-tool-name {
        width: 100%;
        color: $warning;
        text-style: bold;
    }
    ToolApprovalWidget .approval-detail {
        width: 100%;
        color: $text-muted;
        margin-bottom: 1;
    }
    ToolApprovalWidget .approval-buttons {
        width: 100%;
        height: 3;
    }
    ToolApprovalWidget .approval-buttons Button {
        margin-right: 1;
    }
    """

    class Decided(TMessage):
        """Posted when the user approves or denies."""

        def __init__(self, tool_use_id: str, approved: bool) -> None:
            super().__init__()
            self.tool_use_id = tool_use_id
            self.approved = approved

    def __init__(self, tool_use_id: str, tool_name: str, tool_input: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tool_use_id = tool_use_id
        self._tool_name = tool_name
        self._tool_input = tool_input

    def compose(self) -> ComposeResult:
        summary = _tool_summary(self._tool_name, self._tool_input)
        yield Label(f"Tool approval needed: {self._tool_name}", classes="approval-tool-name")
        yield Label(summary, classes="approval-detail")
        with Horizontal(classes="approval-buttons"):
            yield Button("Approve", id="btn-approve", variant="success")
            yield Button("Deny", id="btn-deny", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        approved = event.button.id == "btn-approve"
        self.post_message(self.Decided(self._tool_use_id, approved))
        # Replace buttons with decision text
        try:
            label = "Approved" if approved else "Denied"
            for btn in self.query(Button):
                btn.remove()
            self.mount(Label(f"[{label}]", classes="approval-detail"))
        except Exception:
            pass
