"""Collapsible sidebar section grouping sessions by workspace."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Click
from textual.message import Message as TMessage
from textual.widgets import Label


class _ClickLabel(Label):
    """A Label that posts Pressed when clicked."""

    class Pressed(TMessage):
        def __init__(self, action: str) -> None:
            super().__init__()
            self.action = action

    def __init__(self, text: str, action: str, **kwargs) -> None:
        super().__init__(text, **kwargs)
        self._action = action

    def on_click(self, event: Click) -> None:
        event.stop()
        self.post_message(self.Pressed(self._action))


class WorkspaceSection(Vertical):
    """A collapsible workspace section in the sidebar."""

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
        height: 1;
        color: $text;
        text-style: bold;
    }
    WorkspaceSection .ws-spacer {
        width: 1fr;
        height: 1;
    }
    WorkspaceSection .ws-btn {
        width: auto;
        min-width: 3;
        height: 1;
        color: $text-muted;
    }
    WorkspaceSection .ws-btn:hover {
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

    class RefreshWorkspaceRequested(TMessage):
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
        with Horizontal(classes="ws-header"):
            yield Label(arrow, classes="ws-arrow", id=f"ws-arrow-{id(self)}")
            yield Label(
                f"[bold {self._color}]{self._workspace_name}[/bold {self._color}]",
                classes="ws-name",
                id=f"ws-name-{id(self)}",
                markup=True,
            )
            yield Label("", classes="ws-spacer")  # pushes buttons right
            if self._cwd is not None:
                yield _ClickLabel("r", "refresh", classes="ws-btn")
            yield _ClickLabel("+", "add", classes="ws-btn")
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
        if event.button == 3 and self._cwd is not None:
            event.stop()
            self.post_message(self.RemoveWorkspaceRequested(self._cwd, self._workspace_name))
            return

        target = event.widget
        if isinstance(target, Label) and (
            "ws-arrow" in target.classes or "ws-name" in target.classes
        ):
            event.stop()
            self._toggle_collapse()

    def on__click_label_pressed(self, event: _ClickLabel.Pressed) -> None:
        event.stop()
        if event.action == "add":
            self.post_message(self.NewChatInWorkspace(self._cwd))
        elif event.action == "refresh" and self._cwd is not None:
            self.post_message(self.RefreshWorkspaceRequested(self._cwd, self._workspace_name))

    @property
    def items_container(self) -> Vertical:
        return self.query_one(f"#ws-items-{id(self)}", Vertical)

    def expand(self) -> None:
        if self._collapsed:
            self._toggle_collapse()

    def collapse(self) -> None:
        if not self._collapsed:
            self._toggle_collapse()
