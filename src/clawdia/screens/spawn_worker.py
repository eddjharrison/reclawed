"""Spawn Worker modal — collects task description, model, and permission mode."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, TextArea

from clawdia.config import WorkerTemplate

_NO_TEMPLATE = "__none__"


class SpawnWorkerScreen(ModalScreen[dict | None]):
    """Modal for spawning a new worker session.

    Accepts an optional list of :class:`~reclawed.config.WorkerTemplate` objects.
    When a template is selected, the model and permission dropdowns are
    auto-populated from the template's defaults.  The user can still override
    them manually before confirming.

    Returns a dict on success::

        {
            "task": str,
            "model": str,
            "permission_mode": str,
            "template_id": str | None,
        }

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
    SpawnWorkerScreen #template-label {
        color: $text-muted;
        margin-top: 1;
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

    def __init__(
        self,
        templates: list[WorkerTemplate] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._templates: list[WorkerTemplate] = templates or []
        # Build a fast lookup by id
        self._template_map: dict[str, WorkerTemplate] = {t.id: t for t in self._templates}

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Spawn Worker Session", id="title")

            # Template selector — only shown if templates are available
            if self._templates:
                yield Label("Template:", id="template-label")
                template_options = [("None / Custom", _NO_TEMPLATE)] + [
                    (t.name, t.id) for t in self._templates
                ]
                yield Select(
                    template_options,
                    value=_NO_TEMPLATE,
                    id="template-select",
                )

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

    def on_select_changed(self, event: Select.Changed) -> None:
        """Auto-populate model and permission dropdowns when a template is selected.

        When the user clears the template selection back to 'None / Custom',
        reset both dropdowns to their original defaults so no stale template
        values remain.
        """
        if event.select.id != "template-select":
            return
        template_id = event.value
        if template_id == _NO_TEMPLATE or template_id is Select.BLANK:
            # Reset to defaults when "None / Custom" is (re-)selected
            try:
                self.query_one("#model-select", Select).value = "sonnet"
            except Exception:
                pass
            try:
                self.query_one("#perm-select", Select).value = "bypassPermissions"
            except Exception:
                pass
            return
        tmpl = self._template_map.get(str(template_id))
        if tmpl is None:
            return
        # Auto-populate model and permission from template defaults
        try:
            self.query_one("#model-select", Select).value = tmpl.model
        except Exception:
            pass
        try:
            self.query_one("#perm-select", Select).value = tmpl.permission_mode
        except Exception:
            pass

    def _selected_template_id(self) -> str | None:
        """Return the currently selected template ID, or None if 'None / Custom'."""
        if not self._templates:
            return None
        try:
            val = self.query_one("#template-select", Select).value
            if val == _NO_TEMPLATE or val is Select.BLANK:
                return None
            return str(val)
        except Exception:
            return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-spawn":
            task = self.query_one("#task-input", TextArea).text.strip()
            if not task:
                self.notify("Task description is required", severity="warning", timeout=3)
                return
            model_val = self.query_one("#model-select", Select).value
            perm_val = self.query_one("#perm-select", Select).value
            # Guard against Select.BLANK (sentinel) if the widget is unset
            model = str(model_val) if model_val is not Select.BLANK else "sonnet"
            perm = str(perm_val) if perm_val is not Select.BLANK else "bypassPermissions"
            template_id = self._selected_template_id()
            self.dismiss({
                "task": task,
                "model": model,
                "permission_mode": perm,
                "template_id": template_id,
            })
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)
