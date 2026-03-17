"""Collapsible sidebar section grouping sessions by workspace."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Click
from textual.message import Message as TMessage
from textual.widgets import Collapsible, Label


class _AddButton(Label):
    """Small clickable [+] button."""

    class Pressed(TMessage):
        """Posted when clicked."""

    def on_click(self, event: Click) -> None:
        event.stop()
        self.post_message(self.Pressed())


class WorkspaceSection(Vertical):
    """A collapsible workspace section in the sidebar.

    Custom header row with expand arrow, workspace name, and [+] button.
    The Collapsible is hidden — we manage collapse state manually.
    """

    DEFAULT_CSS = """
    WorkspaceSection {
        width: 100%;
        height: auto;
    }
    WorkspaceSection .ws-header {
        width: 100%;
        height: 1;
        padding: 0 1;
    }
    WorkspaceSection .ws-arrow {
        width: 2;
        height: 1;
        color: $text;
    }
    WorkspaceSection .ws-name {
        width: 1fr;
        height: 1;
        color: $text;
        text-style: bold;
    }
    WorkspaceSection .ws-header:hover .ws-name {
        color: $accent;
    }
    WorkspaceSection .ws-add {
        width: 3;
        height: 1;
        color: $text-muted;
    }
    WorkspaceSection .ws-add:hover {
        color: $accent;
        text-style: bold;
    }
    WorkspaceSection .ws-items {
        width: 100%;
        height: auto;
    }
    WorkspaceSection .ws-items.hidden {
        display: none;
    }
    """

    class NewChatInWorkspace(TMessage):
        def __init__(self, cwd: str | None) -> None:
            super().__init__()
            self.cwd = cwd

    class RemoveWorkspaceRequested(TMessage):
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
        arrow = "▶" if self._collapsed else "▼"
        with Horizontal(classes="ws-header"):
            yield Label(arrow, classes="ws-arrow", id=f"ws-arrow-{id(self)}")
            yield Label(self._workspace_name, classes="ws-name", id=f"ws-name-{id(self)}")
            yield _AddButton("[+]", classes="ws-add")
        yield Vertical(
            classes="ws-items hidden" if self._collapsed else "ws-items",
            id=f"ws-items-{id(self)}",
        )

    def _toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        arrow = self.query_one(f"#ws-arrow-{id(self)}", Label)
        arrow.update("▶" if self._collapsed else "▼")
        items = self.query_one(f"#ws-items-{id(self)}", Vertical)
        items.toggle_class("hidden")

    def on_click(self, event: Click) -> None:
        # Right-click → remove workspace
        if event.button == 3 and self._cwd is not None:
            event.stop()
            self.post_message(self.RemoveWorkspaceRequested(self._cwd, self._workspace_name))
            return

        # Left-click on the header area (arrow or name) → toggle collapse
        # The _AddButton handles its own click via on__add_button_pressed
        target = event.widget
        if isinstance(target, Label) and (
            "ws-arrow" in target.classes or "ws-name" in target.classes
        ):
            event.stop()
            self._toggle_collapse()

    def on__add_button_pressed(self, event: _AddButton.Pressed) -> None:
        event.stop()
        self.post_message(self.NewChatInWorkspace(self._cwd))

    @property
    def items_container(self) -> Vertical:
        return self.query_one(f"#ws-items-{id(self)}", Vertical)

    def expand(self) -> None:
        """Programmatically expand this section."""
        if self._collapsed:
            self._toggle_collapse()

    def collapse(self) -> None:
        """Programmatically collapse this section."""
        if not self._collapsed:
            self._toggle_collapse()
