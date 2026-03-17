"""Collapsible sidebar section grouping sessions by workspace."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Click
from textual.message import Message as TMessage
from textual.widgets import Collapsible, Label


class WorkspaceSection(Vertical):
    """A collapsible workspace section in the sidebar.

    The Collapsible title includes a '[+]' suffix. Clicking it posts
    ``NewChatInWorkspace(cwd)``.
    """

    DEFAULT_CSS = """
    WorkspaceSection {
        width: 100%;
        height: auto;
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
        title = f"{self._workspace_name}  [+]"
        with Collapsible(title=title, collapsed=self._collapsed):
            yield Vertical(id=f"ws-items-{id(self)}")

    def on_click(self, event: Click) -> None:
        if event.button == 3 and self._cwd is not None:
            # Right-click → remove workspace
            event.stop()
            self.post_message(self.RemoveWorkspaceRequested(self._cwd, self._workspace_name))
            return

        # Left-click on the header row — check if they clicked the [+] area
        # The [+] is at the end of the title, so check if click x is far right
        if event.button == 1 and event.y == 0:
            # Header row is y=0. The [+] occupies the last few chars.
            # Get the widget width and check if click is in the right portion
            width = self.size.width
            if event.x >= width - 6:
                event.stop()
                self.post_message(self.NewChatInWorkspace(self._cwd))

    @property
    def items_container(self) -> Vertical:
        """Return the container where ChatListItem widgets should be mounted."""
        return self.query_one(f"#ws-items-{id(self)}", Vertical)
