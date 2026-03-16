"""Collapsible sidebar section grouping sessions by workspace."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Click
from textual.message import Message as TMessage
from textual.widgets import Collapsible, Label


class _NewChatLabel(Label):
    """A Label that posts a message when clicked."""

    class Pressed(TMessage):
        """Posted when this label is clicked."""

    def on_click(self, event: Click) -> None:
        event.stop()
        self.post_message(self.Pressed())


class WorkspaceSection(Vertical):
    """A collapsible workspace section in the sidebar.

    Contains ChatListItem widgets and a clickable '+ New Chat' label.
    Posts ``NewChatInWorkspace(cwd)`` when the add label is clicked.
    """

    DEFAULT_CSS = """
    WorkspaceSection {
        width: 100%;
        height: auto;
    }
    WorkspaceSection .ws-new-chat {
        width: 100%;
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    WorkspaceSection .ws-new-chat:hover {
        color: $accent;
        text-style: bold;
    }
    """

    class NewChatInWorkspace(TMessage):
        """Posted when '+ New Chat' is clicked inside a workspace section."""

        def __init__(self, cwd: str | None) -> None:
            super().__init__()
            self.cwd = cwd

    class RemoveWorkspaceRequested(TMessage):
        """Posted when the user requests to remove a workspace."""

        def __init__(self, cwd: str, name: str) -> None:
            super().__init__()
            self.cwd = cwd
            self.name = name

    def __init__(
        self,
        workspace_name: str,
        cwd: str | None = None,
        collapsed: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._workspace_name = workspace_name
        self._cwd = cwd
        self._collapsed = collapsed

    def compose(self) -> ComposeResult:
        with Collapsible(title=self._workspace_name, collapsed=self._collapsed):
            yield Vertical(id=f"ws-items-{id(self)}")
            yield _NewChatLabel("+ New Chat", classes="ws-new-chat")

    def on__new_chat_label_pressed(self, event: _NewChatLabel.Pressed) -> None:
        event.stop()
        self.post_message(self.NewChatInWorkspace(self._cwd))

    def on_click(self, event: Click) -> None:
        # Right-click on workspace header → remove workspace
        if event.button == 3 and self._cwd is not None:
            event.stop()
            self.post_message(self.RemoveWorkspaceRequested(self._cwd, self._workspace_name))

    @property
    def items_container(self) -> Vertical:
        """Return the container where ChatListItem widgets should be mounted."""
        return self.query_one(f"#ws-items-{id(self)}", Vertical)
