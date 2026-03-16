"""Settings screen for workspace discovery and session import."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label

from reclawed.config import Config, Workspace
from reclawed.importer import (
    DiscoveredProject,
    discover_projects,
    import_project_sessions,
)
from reclawed.store import Store


class SettingsScreen(ModalScreen[bool]):
    """Modal screen for workspace discovery, import, and manual path entry.

    Returns ``True`` when workspaces were changed, ``None`` on close.
    """

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }
    SettingsScreen > #settings-dialog {
        width: 80;
        height: auto;
        max-height: 34;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    SettingsScreen #settings-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    SettingsScreen .section-header {
        width: 100%;
        color: $text-muted;
        margin-top: 1;
    }
    SettingsScreen #project-list {
        width: 100%;
        height: 12;
        border: solid $primary 30%;
        margin-bottom: 1;
    }
    SettingsScreen .project-row {
        width: 100%;
        height: auto;
    }
    SettingsScreen .project-row Checkbox {
        width: auto;
        padding: 0;
        margin: 0;
    }
    SettingsScreen .project-row Label {
        width: 1fr;
        padding: 0 1;
    }
    SettingsScreen #add-row {
        width: 100%;
        height: 3;
        margin-bottom: 1;
    }
    SettingsScreen #add-path-input {
        width: 1fr;
    }
    SettingsScreen #btn-add {
        width: 10;
    }
    SettingsScreen #status-line {
        width: 100%;
        color: $success;
        height: 1;
        margin-bottom: 1;
    }
    SettingsScreen #button-bar {
        width: 100%;
        height: 3;
        align-horizontal: right;
    }
    SettingsScreen #button-bar Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
    ]

    def __init__(self, config: Config, store: Store, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._store = store
        self._projects: list[DiscoveredProject] = []
        # Track which projects are checked (by cwd)
        self._checked: set[str] = set()
        self._changed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Label("Settings", id="settings-title")
            yield Label("── Discovered Projects ──", classes="section-header")
            yield VerticalScroll(id="project-list")
            yield Label("── Add Workspace Manually ──", classes="section-header")
            with Horizontal(id="add-row"):
                yield Input(
                    placeholder="Path to project directory...",
                    id="add-path-input",
                )
                yield Button("Add", id="btn-add")
            yield Label("", id="status-line")
            with Horizontal(id="button-bar"):
                yield Button("Import & Save", id="btn-import", variant="primary")
                yield Button("Close", id="btn-close")

    async def on_mount(self) -> None:
        self._set_status("Scanning for projects...")
        # Discover in a thread to avoid blocking
        projects = await asyncio.to_thread(discover_projects)
        self._projects = projects
        self._populate_project_list()
        self._set_status(f"Found {len(projects)} projects")

    def _populate_project_list(self) -> None:
        """Build the checkbox list from discovered projects."""
        project_list = self.query_one("#project-list", VerticalScroll)
        project_list.remove_children()

        # Pre-check projects already in config workspaces
        existing_paths = {ws.expanded_path for ws in self._config.workspaces}

        for project in self._projects:
            is_enabled = project.cwd in existing_paths
            if is_enabled:
                self._checked.add(project.cwd)

            row = Horizontal(classes="project-row")
            project_list.mount(row)
            cb = Checkbox(
                value=is_enabled,
                id=f"cb-{id(project)}",
            )
            cb._project_cwd = project.cwd  # type: ignore[attr-defined]
            row.mount(cb)
            row.mount(Label(
                f"{project.cwd} ({project.session_count} sessions)",
            ))

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        cwd = getattr(event.checkbox, "_project_cwd", None)
        if cwd is None:
            return
        if event.value:
            self._checked.add(cwd)
        else:
            self._checked.discard(cwd)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-add":
            self._handle_add_path()
        elif event.button.id == "btn-import":
            self._handle_import()
        elif event.button.id == "btn-close":
            self._dismiss_screen()

    def _handle_add_path(self) -> None:
        """Add a manual workspace path."""
        path_input = self.query_one("#add-path-input", Input)
        raw_path = path_input.value.strip()
        if not raw_path:
            return

        expanded = str(Path(raw_path).expanduser().resolve())
        if not Path(expanded).is_dir():
            self._set_status(f"Directory not found: {expanded}")
            return

        # Check if already in the list
        if expanded in self._checked:
            self._set_status(f"Already added: {expanded}")
            return

        # Add as a discovered project (session_count=0 for manual)
        project = DiscoveredProject(
            cwd=expanded,
            session_count=0,
            project_dir=Path.home() / ".claude" / "projects",  # placeholder
        )
        self._projects.append(project)
        self._checked.add(expanded)

        # Add row to UI
        project_list = self.query_one("#project-list", VerticalScroll)
        row = Horizontal(classes="project-row")
        project_list.mount(row)
        cb = Checkbox(value=True, id=f"cb-{id(project)}")
        cb._project_cwd = expanded  # type: ignore[attr-defined]
        row.mount(cb)
        row.mount(Label(f"{expanded} (manual)"))

        path_input.value = ""
        self._set_status(f"Added: {expanded}")

    @work(thread=False)
    async def _handle_import(self) -> None:
        """Import sessions for all checked projects and save config."""
        checked_cwds = set(self._checked)
        if not checked_cwds:
            self._set_status("No projects selected")
            return

        # Build new workspace list from checked projects
        new_workspaces: list[Workspace] = []
        for cwd in sorted(checked_cwds):
            # Reuse existing workspace name if available
            existing = self._config.workspace_for_cwd(cwd)
            if existing:
                new_workspaces.append(existing)
            else:
                # Derive name from last path component
                name = Path(cwd).name or cwd
                new_workspaces.append(Workspace(name=name, path=cwd))

        self._config.workspaces = new_workspaces

        # Import sessions for projects that have JSONL files
        total_imported = 0
        projects_with_files = [
            p for p in self._projects
            if p.cwd in checked_cwds and p.session_count > 0
        ]

        for i, project in enumerate(projects_with_files, 1):
            self._set_status(
                f"Importing {i}/{len(projects_with_files)}: "
                f"{Path(project.cwd).name}..."
            )
            count = import_project_sessions(project, self._store)
            total_imported += count

        # Save config
        self._config.save()
        self._changed = True
        self._set_status(
            f"Done! Imported {total_imported} sessions, "
            f"{len(new_workspaces)} workspaces saved"
        )

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#status-line", Label).update(text)
        except Exception:
            pass

    def _dismiss_screen(self) -> None:
        self.dismiss(self._changed or None)

    def action_close(self) -> None:
        self._dismiss_screen()


class DisplayNameScreen(ModalScreen[str | None]):
    """Small modal for changing the participant display name."""

    DEFAULT_CSS = """
    DisplayNameScreen {
        align: center middle;
    }
    DisplayNameScreen > #name-dialog {
        width: 50;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    DisplayNameScreen #name-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    DisplayNameScreen #name-input {
        width: 100%;
        margin-bottom: 1;
    }
    DisplayNameScreen #name-buttons {
        width: 100%;
        height: 3;
        align-horizontal: right;
    }
    DisplayNameScreen #name-buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def __init__(self, current_name: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_name = current_name

    def compose(self) -> ComposeResult:
        with Vertical(id="name-dialog"):
            yield Label("Change Display Name", id="name-title")
            yield Input(
                value=self._current_name,
                placeholder="Your display name...",
                id="name-input",
            )
            with Horizontal(id="name-buttons"):
                yield Button("Save", id="btn-name-save", variant="primary")
                yield Button("Cancel", id="btn-name-cancel")

    def on_mount(self) -> None:
        self.query_one("#name-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-name-save":
            name = self.query_one("#name-input", Input).value.strip()
            if name:
                self.dismiss(name)
            else:
                self.dismiss(None)
        elif event.button.id == "btn-name-cancel":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "name-input":
            name = event.value.strip()
            self.dismiss(name if name else None)

    def action_cancel(self) -> None:
        self.dismiss(None)
