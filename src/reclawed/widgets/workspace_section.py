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


class _RefreshButton(Label):
    """Small clickable refresh button."""

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

    class RefreshWorkspaceRequested(TMessage):
        """Posted when the user clicks the refresh button to re-import sessions."""
        def __init__(self, cwd: str, name: str) -> None:
            super().__init__()
            self.cwd = cwd
            self.name = name

    def __init__(
        self,
        workspace_name: str,
        cwd: str | None = None,
        collapsed: bool = True,
        color: str = "cyan",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._workspace_name = workspace_name
        self._cwd = cwd
        self._collapsed = collapsed
        self._color = color

    def compose(self) -> ComposeResult:
        arrow = "▶" if self._collapsed else "▼"
        btns = " [r][+]" if self._cwd is not None else " [+]"
        with Horizontal(classes="ws-header"):
            yield Label(arrow, classes="ws-arrow", id=f"ws-arrow-{id(self)}")
            yield Label(
                f"[bold {self._color}]{self._workspace_name}[/bold {self._color}][dim]{btns}[/dim]",
                classes="ws-name",
                id=f"ws-name-{id(self)}",
                markup=True,
            )
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

        # Left-click on the name label — check if they clicked [r] or [+]
        target = event.widget
        if isinstance(target, Label) and "ws-name" in target.classes:
            event.stop()
            # Detect click position within the rendered text
            # The text ends with " [r][+]" or " [+]"
            rendered = target.render().plain if hasattr(target.render(), 'plain') else str(target.render())
            click_x = event.x
            text_len = len(rendered)

            if self._cwd is not None:
                # Has [r][+] — last 6 chars are "[r][+]"
                if click_x >= text_len - 3:
                    self.post_message(self.NewChatInWorkspace(self._cwd))
                    return
                elif click_x >= text_len - 6:
                    self.post_message(self.RefreshWorkspaceRequested(self._cwd, self._workspace_name))
                    return
            else:
                # Just [+] — last 3 chars
                if click_x >= text_len - 3:
                    self.post_message(self.NewChatInWorkspace(self._cwd))
                    return

            self._toggle_collapse()
            return

        if isinstance(target, Label) and "ws-arrow" in target.classes:
            event.stop()
            self._toggle_collapse()

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
