"""Inline spawn proposal buttons for orchestrator-initiated worker delegation."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message as TMessage
from textual.widgets import Button, Label


class SpawnProposalsWidget(Vertical):
    """Renders worker spawn proposals detected in an orchestrator response.

    Posts ``SpawnProposalsWidget.SpawnRequested(proposals, orchestrator_session_id)``
    when the user clicks "Spawn All" or an individual "Spawn" button.

    Each proposal dict may include an optional ``template_id`` key; when
    present the template name is shown as a tag alongside the model/permissions.
    """

    DEFAULT_CSS = """
    SpawnProposalsWidget {
        width: 100%;
        height: auto;
        margin: 1 0;
        padding: 0 1;
        border-left: thick $success;
        background: $surface;
    }
    SpawnProposalsWidget .proposals-header {
        width: 100%;
        color: $success;
        text-style: bold;
        margin-bottom: 1;
    }
    SpawnProposalsWidget .proposal-row {
        width: 100%;
        height: auto;
    }
    SpawnProposalsWidget .proposal-task {
        width: 1fr;
        color: $text;
    }
    SpawnProposalsWidget .proposal-meta {
        color: $text-muted;
    }
    SpawnProposalsWidget .spawn-buttons {
        width: 100%;
        height: 3;
        margin-top: 1;
    }
    SpawnProposalsWidget .spawn-buttons Button {
        margin-right: 1;
    }
    """

    class SpawnRequested(TMessage):
        """Posted when user approves spawning workers."""

        def __init__(self, proposals: list[dict], orchestrator_session_id: str) -> None:
            super().__init__()
            self.proposals = proposals
            self.orchestrator_session_id = orchestrator_session_id

    def __init__(
        self,
        proposals: list[dict],
        orchestrator_session_id: str,
        template_names: dict[str, str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._proposals = proposals
        self._orchestrator_session_id = orchestrator_session_id
        # Mapping of template_id → human-readable template name for display
        self._template_names: dict[str, str] = template_names or {}

    def compose(self) -> ComposeResult:
        n = len(self._proposals)
        yield Label(
            f"Claude proposes {n} worker{'s' if n != 1 else ''}:",
            classes="proposals-header",
        )
        for i, p in enumerate(self._proposals):
            model = p.get("model", "sonnet")
            perm = p.get("permission_mode", "bypassPermissions")
            template_id = p.get("template_id")
            # Build the meta line: "sonnet / bypassPermissions" or
            # "sonnet / bypassPermissions  [Implementation Sprint]"
            meta = f"{model} / {perm}"
            if template_id:
                tmpl_name = self._template_names.get(template_id, template_id)
                meta += f"  [{tmpl_name}]"
            with Vertical(classes="proposal-row"):
                yield Label(f"  {i + 1}. {p['task']}", classes="proposal-task")
                yield Label(f"     {meta}", classes="proposal-meta")
        with Horizontal(classes="spawn-buttons"):
            yield Button(f"Spawn All ({n})", id="btn-spawn-all", variant="success")
            yield Button("Skip", id="btn-skip", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "btn-spawn-all":
            self.post_message(
                self.SpawnRequested(self._proposals, self._orchestrator_session_id)
            )
            self._replace_with_confirmation(len(self._proposals))
        elif event.button.id == "btn-skip":
            self._replace_with_confirmation(0)

    def _replace_with_confirmation(self, count: int) -> None:
        """Replace buttons with a confirmation label."""
        try:
            for btn in self.query(Button):
                btn.remove()
            if count > 0:
                self.mount(Label(
                    f"[Spawned {count} worker{'s' if count != 1 else ''}]",
                    classes="proposals-header",
                ))
            else:
                self.mount(Label("[Skipped]", classes="proposal-meta"))
        except Exception:
            pass
