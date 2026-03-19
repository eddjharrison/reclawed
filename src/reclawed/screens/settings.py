"""Full settings editor with tabs — General, Claude, Group Chat, Workspaces."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Checkbox, Input, Label, Select, Static,
    TabbedContent, TabPane,
)

from reclawed.claude_settings import ClaudeSettingsManager, HookGroup, HookEntry, HOOK_EVENTS
from reclawed.config import Config, Workspace, THEME_MAP
from reclawed.importer import (
    DiscoveredProject,
    discover_projects,
    import_project_sessions,
)
from reclawed.store import Store


class HookEditorScreen(ModalScreen["dict | None"]):
    """Modal for adding a new hook."""

    DEFAULT_CSS = """
    HookEditorScreen {
        align: center middle;
    }
    HookEditorScreen > #hook-dialog {
        width: 70;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    HookEditorScreen .field-row {
        width: 100%;
        height: 3;
    }
    HookEditorScreen .field-label {
        width: 15;
        padding: 1 1 0 0;
    }
    HookEditorScreen .field-input {
        width: 1fr;
    }
    """

    BINDINGS = [Binding("escape", "cancel", priority=True)]

    def compose(self) -> ComposeResult:
        events = [(e, e) for e in HOOK_EVENTS]
        scopes = [("project", "project"), ("user", "user"), ("local", "local")]
        with Vertical(id="hook-dialog"):
            yield Label("Add Hook", id="hook-title")
            with Horizontal(classes="field-row"):
                yield Label("Event", classes="field-label")
                yield Select(events, value="PreToolUse", id="sel-hook-event")
            with Horizontal(classes="field-row"):
                yield Label("Scope", classes="field-label")
                yield Select(scopes, value="project", id="sel-hook-scope")
            with Horizontal(classes="field-row"):
                yield Label("Matcher", classes="field-label")
                yield Input(placeholder="optional regex", id="inp-hook-matcher", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Label("Command", classes="field-label")
                yield Input(placeholder="shell command", id="inp-hook-cmd", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Label("Timeout (ms)", classes="field-label")
                yield Input(placeholder="optional", id="inp-hook-timeout", classes="field-input")
            with Horizontal():
                yield Button("Save", id="btn-hook-save", variant="primary")
                yield Button("Cancel", id="btn-hook-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-hook-save":
            try:
                ev = str(self.query_one("#sel-hook-event", Select).value)
                scope = str(self.query_one("#sel-hook-scope", Select).value)
                matcher = self.query_one("#inp-hook-matcher", Input).value.strip() or None
                cmd = self.query_one("#inp-hook-cmd", Input).value.strip()
                timeout_str = self.query_one("#inp-hook-timeout", Input).value.strip()
                timeout = int(timeout_str) if timeout_str else None
                if not cmd:
                    return
                self.dismiss({"event": ev, "scope": scope, "matcher": matcher, "command": cmd, "timeout": timeout})
            except Exception:
                pass
        elif event.button.id == "btn-hook-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class McpServerEditorScreen(ModalScreen["dict | None"]):
    """Modal for adding a new MCP server."""

    DEFAULT_CSS = """
    McpServerEditorScreen {
        align: center middle;
    }
    McpServerEditorScreen > #mcp-dialog {
        width: 70;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    McpServerEditorScreen .field-row {
        width: 100%;
        height: 3;
    }
    McpServerEditorScreen .field-label {
        width: 15;
        padding: 1 1 0 0;
    }
    McpServerEditorScreen .field-input {
        width: 1fr;
    }
    """

    BINDINGS = [Binding("escape", "cancel", priority=True)]

    def compose(self) -> ComposeResult:
        types = [("stdio", "stdio"), ("http", "http"), ("sse", "sse")]
        scopes = [("project", "project"), ("user", "user"), ("local", "local")]
        with Vertical(id="mcp-dialog"):
            yield Label("Add MCP Server")
            with Horizontal(classes="field-row"):
                yield Label("Name", classes="field-label")
                yield Input(placeholder="server-name", id="inp-mcp-name", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Label("Type", classes="field-label")
                yield Select(types, value="stdio", id="sel-mcp-type")
            with Horizontal(classes="field-row"):
                yield Label("Command", classes="field-label")
                yield Input(placeholder="command to run", id="inp-mcp-cmd", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Label("Args", classes="field-label")
                yield Input(placeholder="space-separated args", id="inp-mcp-args", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Label("URL", classes="field-label")
                yield Input(placeholder="http://... (for http/sse)", id="inp-mcp-url", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Label("Scope", classes="field-label")
                yield Select(scopes, value="project", id="sel-mcp-scope")
            with Horizontal():
                yield Button("Save", id="btn-mcp-save", variant="primary")
                yield Button("Cancel", id="btn-mcp-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-mcp-save":
            try:
                name = self.query_one("#inp-mcp-name", Input).value.strip()
                srv_type = str(self.query_one("#sel-mcp-type", Select).value)
                scope = str(self.query_one("#sel-mcp-scope", Select).value)
                if not name:
                    return
                config: dict = {}
                if srv_type == "stdio":
                    cmd = self.query_one("#inp-mcp-cmd", Input).value.strip()
                    if not cmd:
                        return
                    config["command"] = cmd
                    args_str = self.query_one("#inp-mcp-args", Input).value.strip()
                    if args_str:
                        config["args"] = args_str.split()
                else:
                    config["type"] = srv_type
                    url = self.query_one("#inp-mcp-url", Input).value.strip()
                    if not url:
                        return
                    config["url"] = url
                self.dismiss({"name": name, "scope": scope, "config": config})
            except Exception:
                pass
        elif event.button.id == "btn-mcp-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SettingsScreen(ModalScreen[bool]):
    """Tabbed settings editor.

    Returns ``True`` when config was changed, ``None`` on close.
    """

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }
    SettingsScreen > #settings-dialog {
        width: 85;
        height: auto;
        max-height: 36;
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
    SettingsScreen .field-row {
        width: 100%;
        height: 3;
    }
    SettingsScreen .field-label {
        width: 22;
        padding: 1 1 0 0;
    }
    SettingsScreen .field-input {
        width: 1fr;
    }
    SettingsScreen .field-select {
        width: 1fr;
    }
    SettingsScreen #project-list {
        width: 100%;
        height: 10;
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
    SettingsScreen > #settings-dialog {
        width: 95;
        max-height: 42;
    }
    SettingsScreen .scope-badge { width: 9; color: $text-muted; }
    SettingsScreen .scope-project { color: green; }
    SettingsScreen .scope-user { color: cyan; }
    SettingsScreen .scope-local { color: yellow; }
    SettingsScreen .hook-row {
        width: 100%;
        height: auto;
        max-height: 5;
        border-left: thick $primary 30%;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    SettingsScreen .hook-header {
        width: 100%;
        height: 1;
    }
    SettingsScreen .hook-event { width: 20; text-style: bold; }
    SettingsScreen .hook-detail { width: 1fr; height: 1; color: $text-muted; }
    SettingsScreen .hook-remove { width: 10; min-width: 10; height: 3; }
    SettingsScreen #hooks-list { width: 100%; height: auto; max-height: 22; }
    SettingsScreen #mcp-list { width: 100%; height: auto; max-height: 22; }
    SettingsScreen .mcp-row {
        width: 100%;
        height: 1;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    SettingsScreen .mcp-name { width: 24; text-style: bold; }
    SettingsScreen .mcp-type { width: 8; color: $text-muted; }
    SettingsScreen .mcp-status { width: 12; }
    SettingsScreen .mcp-status-connected { color: green; }
    SettingsScreen .mcp-status-failed { color: red; }
    SettingsScreen .mcp-status-disabled { color: $text-disabled; }
    SettingsScreen .mcp-status-pending { color: yellow; }
    SettingsScreen .mcp-status-unknown { color: $text-disabled; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
    ]

    def __init__(
        self,
        config: Config,
        store: Store,
        project_dir: str | None = None,
        claude_session=None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._store = store
        self._project_dir = project_dir
        self._claude_session = claude_session
        self._projects: list[DiscoveredProject] = []
        self._checked: set[str] = set()
        self._changed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Label("Settings", id="settings-title")
            with TabbedContent():
                with TabPane("General", id="tab-general"):
                    yield from self._general_fields()
                with TabPane("Claude", id="tab-claude"):
                    yield from self._claude_fields()
                with TabPane("Group Chat", id="tab-group"):
                    yield from self._group_fields()
                with TabPane("Workspaces", id="tab-workspaces"):
                    yield from self._workspace_fields()
                with TabPane("Hooks", id="tab-hooks"):
                    yield from self._hooks_fields()
                with TabPane("MCP", id="tab-mcp"):
                    yield from self._mcp_fields()
            yield Label("", id="status-line")
            with Horizontal(id="button-bar"):
                yield Button("Save", id="btn-save", variant="primary")
                yield Button("Close", id="btn-close")

    def _general_fields(self) -> ComposeResult:
        themes = [(name, name) for name in THEME_MAP.keys()]
        with Horizontal(classes="field-row"):
            yield Label("Theme", classes="field-label")
            yield Select(themes, value=self._config.theme, id="sel-theme", classes="field-select")
        with Horizontal(classes="field-row"):
            yield Label("Display Name", classes="field-label")
            yield Input(value=self._config.participant_name, id="inp-name", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Label("Claude Binary", classes="field-label")
            yield Input(value=self._config.claude_binary, id="inp-binary", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Label("Stream Throttle (ms)", classes="field-label")
            yield Input(value=str(self._config.stream_throttle_ms), id="inp-throttle", classes="field-input")

    def _claude_fields(self) -> ComposeResult:
        perms = [
            ("default", "default"),
            ("acceptEdits", "acceptEdits"),
            ("bypassPermissions", "bypassPermissions"),
        ]
        with Horizontal(classes="field-row"):
            yield Label("Permission Mode", classes="field-label")
            yield Select(perms, value=self._config.permission_mode, id="sel-perms", classes="field-select")
        with Horizontal(classes="field-row"):
            yield Label("Allowed Tools", classes="field-label")
            yield Input(value=self._config.allowed_tools, id="inp-tools", classes="field-input")

    def _group_fields(self) -> ComposeResult:
        modes = [
            ("Humans Only", "humans_only"),
            ("Claude Assists", "claude_assists"),
            ("Full Auto", "full_auto"),
            ("Claude-to-Claude", "claude_to_claude"),
        ]
        # Map old mode names for display
        respond_val = {"own": "claude_assists", "mentions": "humans_only", "all": "full_auto", "off": "humans_only"}.get(
            self._config.group_auto_respond, self._config.group_auto_respond
        )
        with Horizontal(classes="field-row"):
            yield Label("Default Room Mode", classes="field-label")
            yield Select(modes, value=respond_val, id="sel-room-mode", classes="field-select")
        ctx_modes = [("Isolated", "isolated"), ("Shared History", "shared_history")]
        with Horizontal(classes="field-row"):
            yield Label("Context Mode", classes="field-label")
            yield Select(ctx_modes, value=self._config.group_context_mode, id="sel-ctx-mode", classes="field-select")
        with Horizontal(classes="field-row"):
            yield Label("Context Window", classes="field-label")
            yield Input(value=str(self._config.group_context_window), id="inp-ctx-window", classes="field-input")
        relay_modes = [("Local (auto daemon)", "local"), ("Remote (external server)", "remote")]
        with Horizontal(classes="field-row"):
            yield Label("Relay Mode", classes="field-label")
            yield Select(relay_modes, value=self._config.relay_mode, id="sel-relay-mode", classes="field-select")
        with Horizontal(classes="field-row"):
            yield Label("Relay Port", classes="field-label")
            yield Input(value=str(self._config.relay_port), id="inp-relay-port", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Label("Relay URL", classes="field-label")
            yield Input(value=self._config.relay_url or "", id="inp-relay-url", placeholder="wss://relay.example.com", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Label("Relay Token", classes="field-label")
            yield Input(value=self._config.relay_token or "", id="inp-relay-token", placeholder="shared-secret", classes="field-input")

    def _workspace_fields(self) -> ComposeResult:
        yield Label("Discovered projects will appear here on load.", id="ws-hint")
        yield VerticalScroll(id="project-list")
        with Horizontal(id="add-row"):
            yield Input(placeholder="Path to project directory...", id="add-path-input")
            yield Button("Add", id="btn-add")
        yield Button("Import Selected", id="btn-import", variant="primary")

    def _hooks_fields(self) -> ComposeResult:
        yield Label("", id="hooks-summary")
        yield Button("Manage Hooks", id="btn-manage-hooks", variant="primary")

    def _mcp_fields(self) -> ComposeResult:
        yield Label("", id="mcp-summary")
        yield Button("Manage MCP Servers", id="btn-manage-mcp", variant="primary")

    async def on_mount(self) -> None:
        self._update_hooks_summary()
        self._update_mcp_summary()
        self._set_status("Scanning for projects...")
        projects = await asyncio.to_thread(discover_projects)
        self._projects = projects
        self._populate_project_list()
        self._set_status(f"Found {len(projects)} projects")

    def _populate_project_list(self) -> None:
        project_list = self.query_one("#project-list", VerticalScroll)
        project_list.remove_children()
        existing_paths = {ws.expanded_path for ws in self._config.workspaces}
        for project in self._projects:
            is_enabled = project.cwd in existing_paths
            if is_enabled:
                self._checked.add(project.cwd)
            row = Horizontal(classes="project-row")
            project_list.mount(row)
            cb = Checkbox(value=is_enabled, id=f"cb-{id(project)}")
            cb._project_cwd = project.cwd  # type: ignore[attr-defined]
            row.mount(cb)
            row.mount(Label(f"{project.cwd} ({project.session_count} sessions)"))

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        cwd = getattr(event.checkbox, "_project_cwd", None)
        if cwd is None:
            return
        if event.value:
            self._checked.add(cwd)
        else:
            self._checked.discard(cwd)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self._save_all_settings()
        elif event.button.id == "btn-close":
            self._dismiss_screen()
        elif event.button.id == "btn-add":
            self._handle_add_path()
        elif event.button.id == "btn-import":
            self._handle_import()
        elif event.button.id == "btn-manage-hooks":
            self._open_hooks_manager()
        elif event.button.id == "btn-manage-mcp":
            self._open_mcp_manager()

    def _save_all_settings(self) -> None:
        """Collect all field values and save to config."""
        c = self._config

        # General tab
        try:
            sel = self.query_one("#sel-theme", Select)
            if sel.value and sel.value != Select.BLANK:
                c.theme = str(sel.value)
        except Exception:
            pass
        try:
            c.participant_name = self.query_one("#inp-name", Input).value.strip() or c.participant_name
        except Exception:
            pass
        try:
            c.claude_binary = self.query_one("#inp-binary", Input).value.strip() or c.claude_binary
        except Exception:
            pass
        try:
            c.stream_throttle_ms = int(self.query_one("#inp-throttle", Input).value)
        except (ValueError, Exception):
            pass

        # Claude tab
        try:
            sel = self.query_one("#sel-perms", Select)
            if sel.value and sel.value != Select.BLANK:
                c.permission_mode = str(sel.value)
        except Exception:
            pass
        try:
            c.allowed_tools = self.query_one("#inp-tools", Input).value.strip() or c.allowed_tools
        except Exception:
            pass

        # Group tab
        try:
            sel = self.query_one("#sel-room-mode", Select)
            if sel.value and sel.value != Select.BLANK:
                c.group_auto_respond = str(sel.value)
        except Exception:
            pass
        try:
            sel = self.query_one("#sel-ctx-mode", Select)
            if sel.value and sel.value != Select.BLANK:
                c.group_context_mode = str(sel.value)
        except Exception:
            pass
        try:
            c.group_context_window = int(self.query_one("#inp-ctx-window", Input).value)
        except (ValueError, Exception):
            pass
        try:
            sel = self.query_one("#sel-relay-mode", Select)
            if sel.value and sel.value != Select.BLANK:
                c.relay_mode = str(sel.value)
        except Exception:
            pass
        try:
            c.relay_port = int(self.query_one("#inp-relay-port", Input).value)
        except (ValueError, Exception):
            pass
        try:
            url = self.query_one("#inp-relay-url", Input).value.strip()
            c.relay_url = url if url else None
        except Exception:
            pass
        try:
            token = self.query_one("#inp-relay-token", Input).value.strip()
            c.relay_token = token if token else None
        except Exception:
            pass

        # Workspaces — update from checked projects
        self._update_workspaces_from_checked()

        c.save()
        self._changed = True
        self._set_status("Settings saved!")

        # Apply theme immediately if the app supports it
        try:
            self.app.theme = c.textual_theme
        except Exception:
            pass

    def _update_workspaces_from_checked(self) -> None:
        """Sync config workspaces with checked projects."""
        if not self._checked and not self._config.workspaces:
            return
        new_workspaces: list[Workspace] = []
        for cwd in sorted(self._checked):
            existing = self._config.workspace_for_cwd(cwd)
            if existing:
                new_workspaces.append(existing)
            else:
                name = Path(cwd).name or cwd
                new_workspaces.append(Workspace(name=name, path=cwd))
        self._config.workspaces = new_workspaces

    def _handle_add_path(self) -> None:
        path_input = self.query_one("#add-path-input", Input)
        raw_path = path_input.value.strip()
        if not raw_path:
            return
        expanded = str(Path(raw_path).expanduser().resolve())
        if not Path(expanded).is_dir():
            self._set_status(f"Directory not found: {expanded}")
            return
        if expanded in self._checked:
            self._set_status(f"Already added: {expanded}")
            return
        project = DiscoveredProject(cwd=expanded, session_count=0, project_dir=Path.home() / ".claude" / "projects")
        self._projects.append(project)
        self._checked.add(expanded)
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
        checked_cwds = set(self._checked)
        if not checked_cwds:
            self._set_status("No projects selected")
            return
        self._update_workspaces_from_checked()
        total_imported = 0
        projects_with_files = [p for p in self._projects if p.cwd in checked_cwds and p.session_count > 0]
        for i, project in enumerate(projects_with_files, 1):
            self._set_status(f"Importing {i}/{len(projects_with_files)}: {Path(project.cwd).name}...")
            count = import_project_sessions(project, self._store)
            total_imported += count
        self._config.save()
        self._changed = True
        self._set_status(f"Imported {total_imported} sessions, {len(self._config.workspaces)} workspaces saved")

    def _update_hooks_summary(self) -> None:
        """Update the hooks tab summary label."""
        mgr = ClaudeSettingsManager(project_dir=self._project_dir)
        hooks = mgr.load_hooks()
        try:
            label = self.query_one("#hooks-summary", Label)
        except Exception:
            return
        if not hooks:
            label.update("No hooks configured")
        else:
            events = sorted({h.event for h in hooks})
            label.update(
                f"{len(hooks)} hooks: {', '.join(events)}\n"
                "Click Manage Hooks to view, edit, add, remove, or change scope."
            )

    def _open_hooks_manager(self) -> None:
        from reclawed.screens.hooks_manager import HooksManagerScreen

        def on_dismiss(changed: bool) -> None:
            if changed:
                self._changed = True
                self._update_hooks_summary()

        self.app.push_screen(
            HooksManagerScreen(project_dir=self._project_dir),
            on_dismiss,
        )

    def _update_mcp_summary(self) -> None:
        """Update the MCP tab summary label."""
        mgr = ClaudeSettingsManager(project_dir=self._project_dir)
        servers = mgr.load_mcp_servers()
        try:
            label = self.query_one("#mcp-summary", Label)
        except Exception:
            return
        if not servers:
            label.update("No MCP servers configured")
        else:
            names = sorted(s.name for s in servers)
            label.update(
                f"{len(servers)} servers: {', '.join(names)}\n"
                "Click Manage MCP Servers to view status, authenticate, enable/disable, or add servers."
            )

    def _open_mcp_manager(self) -> None:
        from reclawed.screens.mcp_manager import McpManagerScreen

        def on_dismiss(changed: bool) -> None:
            if changed:
                self._changed = True
                self._update_mcp_summary()

        self.app.push_screen(
            McpManagerScreen(
                project_dir=self._project_dir,
                claude_session=self._claude_session,
            ),
            on_dismiss,
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
            yield Input(value=self._current_name, placeholder="Your display name...", id="name-input")
            with Horizontal(id="name-buttons"):
                yield Button("Save", id="btn-name-save", variant="primary")
                yield Button("Cancel", id="btn-name-cancel")

    def on_mount(self) -> None:
        self.query_one("#name-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-name-save":
            name = self.query_one("#name-input", Input).value.strip()
            self.dismiss(name if name else None)
        elif event.button.id == "btn-name-cancel":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "name-input":
            name = event.value.strip()
            self.dismiss(name if name else None)

    def action_cancel(self) -> None:
        self.dismiss(None)
