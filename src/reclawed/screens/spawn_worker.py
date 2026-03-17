"""Spawn Worker modal — collects task description, model, and permission mode."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, TextArea


class SpawnWorkerScreen(ModalScreen[dict | None]):
    """Modal for spawning a new worker session.

    Returns a dict on success::

        {"task": str, "model": str, "permission_mode": str}

    Returns ``None`` if the user cancels.
    """

    DEFAULT_CSS = """
    SpawnWorkerScreen {
        align: center middle;
    }
    SpawnWorkerScreen > Vertical {
        width: 70;
        height: auto;
        padding: 2 3;
        background: $surface;
        border: tall $primary;
    }
    SpawnWorkerScreen #title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    SpawnWorkerScreen #task-label {
        margin-top: 1;
        color: $text-muted;
    }
    SpawnWorkerScreen TextArea {
        height: 8;
        margin-bottom: 1;
    }
    SpawnWorkerScreen .select-row {
        height: auto;
        margin-bottom: 1;
    }
    SpawnWorkerScreen .select-label {
        width: 12;
        color: $text-muted;
    }
    SpawnWorkerScreen Select {
        width: 1fr;
    }
    SpawnWorkerScreen Horizontal {
        height: auto;
        margin-top: 1;
    }
    SpawnWorkerScreen Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Spawn Worker Session", id="title")
            yield Label("Task description:", id="task-label")
            yield TextArea(id="task-input")
            with Horizontal(classes="select-row"):
                yield Label("Model:", classes="select-label")
                yield Select(
                    [(name, name) for name in ("sonnet", "opus", "haiku")],
                    value="sonnet",
                    id="model-select",
                )
            with Horizontal(classes="select-row"):
                yield Label("Permissions:", classes="select-label")
                yield Select(
                    [
                        ("Default", "default"),
                        ("Accept Edits", "acceptEdits"),
                        ("Bypass Permissions", "bypassPermissions"),
                    ],
                    value="bypassPermissions",
                    id="perm-select",
                )
            with Horizontal():
                yield Button("Spawn", id="btn-spawn", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="error")

    def on_mount(self) -> None:
        self.query_one("#task-input", TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-spawn":
            task = self.query_one("#task-input", TextArea).text.strip()
            if not task:
                self.notify("Task description is required", severity="warning", timeout=3)
                return
            model = self.query_one("#model-select", Select).value
            perm = self.query_one("#perm-select", Select).value
            self.dismiss({"task": task, "model": model, "permission_mode": perm})
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)
