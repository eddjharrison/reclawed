"""Full settings editor with tabs — General, Claude, Group Chat, Workspaces, Templates."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Checkbox, Input, Label, Select, Static, TextArea,
    TabbedContent, TabPane,
)

from reclawed.claude_settings import ClaudeSettingsManager, HookGroup, HookEntry, HOOK_EVENTS
from reclawed.config import BUILTIN_TEMPLATES, Config, Workspace, WorkerTemplate, THEME_MAP, _config_file_path
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

    def __init__(
        self,
        event: str = "PreToolUse",
        scope: str = "project",
        matcher: str = "",
        command: str = "",
        timeout: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._init_event = event
        self._init_scope = scope
        self._init_matcher = matcher
        self._init_command = command
        self._init_timeout = timeout
        self._is_edit = bool(command)

    def compose(self) -> ComposeResult:
        events = [(e, e) for e in HOOK_EVENTS]
        scopes = [("project", "project"), ("user", "user"), ("local", "local")]
        title = "Edit Hook" if self._is_edit else "Add Hook"
        with Vertical(id="hook-dialog"):
            yield Label(title, id="hook-title")
            with Horizontal(classes="field-row"):
                yield Label("Event", classes="field-label")
                yield Select(events, value=self._init_event, id="sel-hook-event")
            with Horizontal(classes="field-row"):
                yield Label("Scope", classes="field-label")
                yield Select(scopes, value=self._init_scope, id="sel-hook-scope")
            with Horizontal(classes="field-row"):
                yield Label("Matcher", classes="field-label")
                yield Input(value=self._init_matcher, placeholder="optional regex", id="inp-hook-matcher", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Label("Command", classes="field-label")
                yield Input(value=self._init_command, placeholder="shell command", id="inp-hook-cmd", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Label("Timeout (ms)", classes="field-label")
                yield Input(value=self._init_timeout, placeholder="optional", id="inp-hook-timeout", classes="field-input")
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
    SettingsScreen .ws-edit-btn {
        width: 3;
        min-width: 3;
        height: 1;
        border: none;
        padding: 0 0;
        margin: 0;
        background: $surface;
        color: $text-muted;
    }
    SettingsScreen .ws-edit-btn:hover {
        color: $primary;
        background: $surface-lighten-1;
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
    SettingsScreen #template-list {
        width: 100%;
        height: 8;
        border: solid $primary 30%;
        margin-bottom: 1;
    }
    SettingsScreen .tmpl-row {
        width: 100%;
        height: 1;
    }
    SettingsScreen .tmpl-icon {
        width: 3;
        color: $text-muted;
    }
    SettingsScreen .tmpl-name {
        width: 1fr;
    }
    SettingsScreen .tmpl-info {
        width: 22;
        color: $text-muted;
    }
    SettingsScreen .tmpl-btn {
        width: 6;
        min-width: 6;
        height: 1;
        border: none;
        padding: 0 0;
        margin: 0 0 0 1;
        background: $surface;
        color: $text-muted;
    }
    SettingsScreen .tmpl-btn:hover {
        color: $primary;
        background: $surface-lighten-1;
    }
    SettingsScreen .tmpl-del:hover {
        color: $error;
    }
    SettingsScreen #btn-new-template {
        width: 18;
        margin-top: 1;
    }
    SettingsScreen #tmpl-hint {
        width: 100%;
        color: $text-muted;
        height: 1;
        margin-bottom: 1;
    }
    SettingsScreen #config-path {
        width: 100%;
        color: $text-muted;
        height: 1;
        margin-bottom: 0;
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
        # Store original theme so we can revert live preview if the user closes without saving.
        self._original_theme = config.theme
        # Per-workspace override edits: expanded_path → {model, permission_mode, allowed_tools}
        self._ws_overrides: dict[str, dict[str, str | None]] = {
            ws.expanded_path: {
                "model": ws.model,
                "permission_mode": ws.permission_mode,
                "allowed_tools": ws.allowed_tools,
            }
            for ws in config.workspaces
        }
        # Dirty-state tracking — True once any field has been edited before Save.
        self._dirty = False
        # True after the first unsaved-close warning; a second Close will dismiss.
        self._close_warned = False
        # Custom (non-builtin) templates being edited in this session.
        self._custom_templates: list[WorkerTemplate] = [
            t for t in config.worker_templates if not t.builtin
        ]

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
                with TabPane("Templates", id="tab-templates"):
                    yield from self._template_fields()
            yield Label(f"Config: {_config_file_path()}", id="config-path")
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
        with Horizontal(classes="field-row"):
            yield Label("Auto-name Sessions", classes="field-label")
            yield Checkbox(value=self._config.auto_name_sessions, id="cb-auto-name")
        with Horizontal(classes="field-row"):
            yield Label("Max Quote Length", classes="field-label")
            yield Input(value=str(self._config.max_quote_length), id="inp-max-quote", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Label("Data Directory", classes="field-label")
            yield Input(value=str(self._config.data_dir), id="inp-data-dir", classes="field-input")

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
            yield Input(
                value=self._config.relay_url or "",
                id="inp-relay-url",
                placeholder="wss://relay.example.com",
                classes="field-input",
            )
        with Horizontal(classes="field-row"):
            yield Label("Relay Token", classes="field-label")
            yield Input(
                value=self._config.relay_token or "",
                id="inp-relay-token",
                placeholder="shared-secret",
                password=True,
                classes="field-input",
            )

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

    def _template_fields(self) -> ComposeResult:
        yield Label(
            "Built-in templates (🔒) are read-only. Custom templates can be edited or deleted.",
            id="tmpl-hint",
        )
        yield VerticalScroll(id="template-list")
        yield Button("＋ New Template", id="btn-new-template")

    async def on_mount(self) -> None:
        self._update_hooks_summary()
        self._update_mcp_summary()
        self._set_status("Scanning for projects...")
        projects = await asyncio.to_thread(discover_projects)
        self._projects = projects
        self._populate_project_list()
        self._populate_template_list()
        self._set_status(f"Found {len(projects)} projects")
        # Apply initial relay-field enabled/disabled state based on current mode.
        self._update_relay_fields(self._config.relay_mode)

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
            edit_btn = Button("⚙", id=f"btn-ws-edit-{id(project)}", classes="ws-edit-btn")
            edit_btn._project_cwd = project.cwd  # type: ignore[attr-defined]
            row.mount(edit_btn)

    def _populate_template_list(self) -> None:
        """Rebuild the template list widget from current config + custom templates."""
        try:
            template_list = self.query_one("#template-list", VerticalScroll)
        except Exception:
            return
        template_list.remove_children()
        # Show builtins first (always), then custom templates
        for tmpl in BUILTIN_TEMPLATES:
            self._mount_template_row(template_list, tmpl)
        for tmpl in self._custom_templates:
            self._mount_template_row(template_list, tmpl)

    def _mount_template_row(self, container: VerticalScroll, tmpl: WorkerTemplate) -> None:
        """Mount a single template row into *container*."""
        icon = "🔒" if tmpl.builtin else "✎"
        info = f"{tmpl.model} / {tmpl.permission_mode}"
        row = Horizontal(classes="tmpl-row", id=f"tmpl-row-{tmpl.id}")
        container.mount(row)
        row.mount(Static(icon, classes="tmpl-icon"))
        row.mount(Label(tmpl.name, classes="tmpl-name"))
        row.mount(Label(info, classes="tmpl-info"))
        if not tmpl.builtin:
            edit_btn = Button("Edit", id=f"btn-tmpl-edit-{tmpl.id}", classes="tmpl-btn")
            edit_btn._template_id = tmpl.id  # type: ignore[attr-defined]
            row.mount(edit_btn)
            del_btn = Button("Del", id=f"btn-tmpl-del-{tmpl.id}", classes="tmpl-btn tmpl-del")
            del_btn._template_id = tmpl.id  # type: ignore[attr-defined]
            row.mount(del_btn)

    # ------------------------------------------------------------------ #
    # Event handlers
    # ------------------------------------------------------------------ #

    def on_select_changed(self, event: Select.Changed) -> None:
        """Live-preview theme; toggle relay fields; mark dirty."""
        if event.select.id == "sel-theme" and event.value and event.value != Select.BLANK:
            try:
                self.app.theme = THEME_MAP.get(str(event.value), "textual-dark")
            except Exception:
                pass
        if event.select.id == "sel-relay-mode" and event.value and event.value != Select.BLANK:
            self._update_relay_fields(str(event.value))
        self._mark_dirty()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        cwd = getattr(event.checkbox, "_project_cwd", None)
        if cwd is None:
            # Non-workspace checkbox (e.g. cb-auto-name) — just mark dirty.
            self._mark_dirty()
            return
        if event.value:
            self._checked.add(cwd)
        else:
            self._checked.discard(cwd)
        self._mark_dirty()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Mark settings as dirty whenever any config input changes."""
        # Ignore the workspace add-path input — it is not a config field.
        if event.input.id == "add-path-input":
            return
        self._mark_dirty()

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
        elif event.button.id and event.button.id.startswith("btn-ws-edit-"):
            cwd = getattr(event.button, "_project_cwd", None)
            if cwd:
                self._open_workspace_config(cwd)
            event.stop()
        elif event.button.id == "btn-new-template":
            self._open_template_editor(None)
            event.stop()
        elif event.button.id and event.button.id.startswith("btn-tmpl-edit-"):
            tmpl_id = event.button.id[len("btn-tmpl-edit-"):]
            self._open_template_editor(tmpl_id)
            event.stop()
        elif event.button.id and event.button.id.startswith("btn-tmpl-del-"):
            tmpl_id = event.button.id[len("btn-tmpl-del-"):]
            self._delete_template(tmpl_id)
            event.stop()

    # ------------------------------------------------------------------ #
    # Dirty-state helpers
    # ------------------------------------------------------------------ #

    def _mark_dirty(self) -> None:
        """Set the dirty flag and append an asterisk to the title."""
        if not self._dirty:
            self._dirty = True
            try:
                self.query_one("#settings-title", Label).update("Settings *")
            except Exception:
                pass
        # Any fresh edit resets the "warned once" flag so the warning fires again.
        self._close_warned = False

    def _clear_dirty(self) -> None:
        """Clear dirty flag and restore the plain title after a successful save."""
        self._dirty = False
        self._close_warned = False
        try:
            self.query_one("#settings-title", Label).update("Settings")
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Relay-field visibility
    # ------------------------------------------------------------------ #

    def _update_relay_fields(self, relay_mode: str) -> None:
        """Enable relay URL / token inputs only when relay_mode is 'remote'."""
        is_remote = relay_mode == "remote"
        for widget_id in ("#inp-relay-url", "#inp-relay-token"):
            try:
                self.query_one(widget_id, Input).disabled = not is_remote
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Workspace-override modal
    # ------------------------------------------------------------------ #

    def _open_workspace_config(self, cwd: str) -> None:
        """Open the WorkspaceConfigModal for a given project path."""
        resolved = str(Path(cwd).expanduser().resolve())
        overrides: dict[str, str | None] = self._ws_overrides.get(
            resolved,
            {"model": None, "permission_mode": None, "allowed_tools": None},
        )

        def _on_result(result: dict[str, str | None] | None) -> None:
            if result is not None:
                self._ws_overrides[resolved] = result
                self._set_status(f"Overrides updated for {Path(cwd).name} (save to persist)")

        self.app.push_screen(WorkspaceConfigModal(cwd, overrides), _on_result)

    # ------------------------------------------------------------------ #
    # Template editor helpers
    # ------------------------------------------------------------------ #

    def _open_template_editor(self, template_id: str | None) -> None:
        """Open WorkerTemplateModal to create (template_id=None) or edit a custom template."""
        existing: WorkerTemplate | None = None
        if template_id is not None:
            existing = next((t for t in self._custom_templates if t.id == template_id), None)

        def _on_result(result: WorkerTemplate | None) -> None:
            if result is None:
                return
            if template_id is None:
                # New template
                self._custom_templates.append(result)
                self._set_status(f"Template '{result.name}' added (save to persist)")
            else:
                # Replace existing
                idx = next(
                    (i for i, t in enumerate(self._custom_templates) if t.id == template_id),
                    None,
                )
                if idx is not None:
                    self._custom_templates[idx] = result
                self._set_status(f"Template '{result.name}' updated (save to persist)")
            self._populate_template_list()
            self._mark_dirty()

        self.app.push_screen(WorkerTemplateModal(existing), _on_result)

    def _delete_template(self, template_id: str) -> None:
        """Remove a custom template by ID and refresh the list."""
        before = len(self._custom_templates)
        self._custom_templates = [t for t in self._custom_templates if t.id != template_id]
        if len(self._custom_templates) < before:
            self._populate_template_list()
            self._set_status("Template deleted (save to persist)")
            self._mark_dirty()

    # ------------------------------------------------------------------ #
    # Validation helpers
    # ------------------------------------------------------------------ #

    def _validate_int(
        self,
        widget_id: str,
        field_name: str,
        min_val: int,
        max_val: int,
    ) -> int | None:
        """Parse an integer Input and validate its range.

        Returns the parsed int on success, or ``None`` and sets an error
        status message on failure.
        """
        try:
            val = int(self.query_one(widget_id, Input).value.strip())
        except (ValueError, Exception):
            self._set_status(f"{field_name} must be a whole number", error=True)
            return None
        if not (min_val <= val <= max_val):
            self._set_status(
                f"{field_name} must be between {min_val} and {max_val}",
                error=True,
            )
            return None
        return val

    # ------------------------------------------------------------------ #
    # Save
    # ------------------------------------------------------------------ #

    def _save_all_settings(self) -> None:
        """Validate all fields, then save to config.  Blocks on validation errors."""
        c = self._config

        # ---- Validate all numeric fields first; bail early on any error ----

        throttle = self._validate_int("#inp-throttle", "Stream Throttle", 10, 5000)
        if throttle is None:
            return

        max_quote = self._validate_int("#inp-max-quote", "Max Quote Length", 50, 2000)
        if max_quote is None:
            return

        ctx_window = self._validate_int("#inp-ctx-window", "Context Window", 1, 100)
        if ctx_window is None:
            return

        relay_port = self._validate_int("#inp-relay-port", "Relay Port", 1024, 65535)
        if relay_port is None:
            return

        # ---- Apply all validated values ----

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
        c.stream_throttle_ms = throttle
        c.max_quote_length = max_quote
        try:
            c.auto_name_sessions = self.query_one("#cb-auto-name", Checkbox).value
        except Exception:
            pass
        try:
            raw = self.query_one("#inp-data-dir", Input).value.strip()
            if raw:
                c.data_dir = Path(raw)
        except Exception:
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
        c.group_context_window = ctx_window
        try:
            sel = self.query_one("#sel-relay-mode", Select)
            if sel.value and sel.value != Select.BLANK:
                c.relay_mode = str(sel.value)
        except Exception:
            pass
        c.relay_port = relay_port
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

        # Templates — rebuild from builtins + current custom list
        c.worker_templates = list(BUILTIN_TEMPLATES) + list(self._custom_templates)

        c.save()
        self._changed = True
        self._clear_dirty()
        self._set_status("Settings saved!")

        # Apply theme immediately if the app supports it
        try:
            self.app.theme = c.textual_theme
        except Exception:
            pass

    def _update_workspaces_from_checked(self) -> None:
        """Sync config workspaces with checked projects, applying any override edits."""
        if not self._checked and not self._config.workspaces:
            return
        new_workspaces: list[Workspace] = []
        for cwd in sorted(self._checked):
            resolved = str(Path(cwd).expanduser().resolve())
            overrides = self._ws_overrides.get(resolved, {})
            existing = self._config.workspace_for_cwd(cwd)
            if existing:
                # Apply any pending override edits to the existing workspace object.
                if "model" in overrides:
                    existing.model = overrides["model"]
                if "permission_mode" in overrides:
                    existing.permission_mode = overrides["permission_mode"]
                if "allowed_tools" in overrides:
                    existing.allowed_tools = overrides["allowed_tools"]
                new_workspaces.append(existing)
            else:
                name = Path(cwd).name or cwd
                new_workspaces.append(Workspace(
                    name=name,
                    path=cwd,
                    model=overrides.get("model"),
                    permission_mode=overrides.get("permission_mode"),
                    allowed_tools=overrides.get("allowed_tools"),
                ))
        self._config.workspaces = new_workspaces

    def _handle_add_path(self) -> None:
        path_input = self.query_one("#add-path-input", Input)
        raw_path = path_input.value.strip()
        if not raw_path:
            return
        expanded = str(Path(raw_path).expanduser().resolve())
        if not Path(expanded).is_dir():
            self._set_status(f"Directory not found: {expanded}", error=True)
            return
        if expanded in self._checked:
            self._set_status(f"Already added: {expanded}", error=True)
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
        edit_btn = Button("⚙", id=f"btn-ws-edit-{abs(hash(expanded))}", classes="ws-edit-btn")
        edit_btn._project_cwd = expanded  # type: ignore[attr-defined]
        row.mount(edit_btn)
        path_input.value = ""
        self._set_status(f"Added: {expanded}")

    @work(thread=False)
    async def _handle_import(self) -> None:
        checked_cwds = set(self._checked)
        if not checked_cwds:
            self._set_status("No projects selected", error=True)
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

    def _set_status(self, text: str, error: bool = False) -> None:
        try:
            label = self.query_one("#status-line", Label)
            label.update(Text(text, style="bold red" if error else "green"))
        except Exception:
            pass

    def _dismiss_screen(self) -> None:
        if self._dirty and not self._changed:
            if not self._close_warned:
                # First unsaved-close attempt: warn instead of dismissing.
                self._close_warned = True
                self._set_status("Unsaved changes! Press Close again to discard.", error=True)
                return
        # Revert live theme preview if the user closes without saving.
        if not self._changed:
            try:
                self.app.theme = THEME_MAP.get(self._original_theme, "textual-dark")
            except Exception:
                pass
        self.dismiss(self._changed or None)

    def action_close(self) -> None:
        self._dismiss_screen()


class WorkspaceConfigModal(ModalScreen[dict | None]):
    """Modal for editing per-workspace model / permission / tools overrides.

    Receives a project *cwd* and the current overrides dict.
    Returns an updated ``{"model": ..., "permission_mode": ..., "allowed_tools": ...}``
    dict on save, or ``None`` on cancel.  Empty-string values are normalised to
    ``None`` (meaning "inherit from global config").
    """

    DEFAULT_CSS = """
    WorkspaceConfigModal {
        align: center middle;
    }
    WorkspaceConfigModal > #wsc-dialog {
        width: 62;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    WorkspaceConfigModal #wsc-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 0;
    }
    WorkspaceConfigModal #wsc-hint {
        width: 100%;
        color: $text-muted;
        margin-bottom: 1;
    }
    WorkspaceConfigModal .wsc-row {
        width: 100%;
        height: 3;
    }
    WorkspaceConfigModal .wsc-label {
        width: 20;
        padding: 1 1 0 0;
    }
    WorkspaceConfigModal .wsc-select {
        width: 1fr;
    }
    WorkspaceConfigModal .wsc-input {
        width: 1fr;
    }
    WorkspaceConfigModal #wsc-buttons {
        width: 100%;
        height: 3;
        align-horizontal: right;
        margin-top: 1;
    }
    WorkspaceConfigModal #wsc-buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    _MODEL_OPTIONS = [
        ("(inherit global)", ""),
        ("sonnet", "sonnet"),
        ("opus", "opus"),
        ("haiku", "haiku"),
    ]
    _PERM_OPTIONS = [
        ("(inherit global)", ""),
        ("default", "default"),
        ("acceptEdits", "acceptEdits"),
        ("bypassPermissions", "bypassPermissions"),
    ]

    def __init__(self, cwd: str, overrides: dict[str, str | None], **kwargs) -> None:
        super().__init__(**kwargs)
        self._cwd = cwd
        self._overrides = overrides

    def compose(self) -> ComposeResult:
        model_val = self._overrides.get("model") or ""
        perm_val = self._overrides.get("permission_mode") or ""
        tools_val = self._overrides.get("allowed_tools") or ""
        name = Path(self._cwd).name or self._cwd
        with Vertical(id="wsc-dialog"):
            yield Label(f"Configure: {name}", id="wsc-title")
            yield Label("Leave a field blank to inherit the global setting.", id="wsc-hint")
            with Horizontal(classes="wsc-row"):
                yield Label("Model", classes="wsc-label")
                yield Select(
                    self._MODEL_OPTIONS,
                    value=model_val,
                    id="sel-wsc-model",
                    classes="wsc-select",
                    allow_blank=False,
                )
            with Horizontal(classes="wsc-row"):
                yield Label("Permission Mode", classes="wsc-label")
                yield Select(
                    self._PERM_OPTIONS,
                    value=perm_val,
                    id="sel-wsc-perms",
                    classes="wsc-select",
                    allow_blank=False,
                )
            with Horizontal(classes="wsc-row"):
                yield Label("Allowed Tools", classes="wsc-label")
                yield Input(
                    value=tools_val,
                    placeholder="(inherit global)",
                    id="inp-wsc-tools",
                    classes="wsc-input",
                )
            with Horizontal(id="wsc-buttons"):
                yield Button("Save", id="btn-wsc-save", variant="primary")
                yield Button("Cancel", id="btn-wsc-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-wsc-save":
            self._do_save()
        elif event.button.id == "btn-wsc-cancel":
            self.dismiss(None)

    def _do_save(self) -> None:
        try:
            model_sel = self.query_one("#sel-wsc-model", Select)
            model: str | None = str(model_sel.value) if model_sel.value and model_sel.value != Select.BLANK else ""
        except Exception:
            model = ""
        try:
            perm_sel = self.query_one("#sel-wsc-perms", Select)
            perm: str | None = str(perm_sel.value) if perm_sel.value and perm_sel.value != Select.BLANK else ""
        except Exception:
            perm = ""
        try:
            tools = self.query_one("#inp-wsc-tools", Input).value.strip()
        except Exception:
            tools = ""
        self.dismiss({
            "model": model if model else None,
            "permission_mode": perm if perm else None,
            "allowed_tools": tools if tools else None,
        })

    def action_cancel(self) -> None:
        self.dismiss(None)


class WorkerTemplateModal(ModalScreen["WorkerTemplate | None"]):
    """Modal for creating or editing a custom :class:`~reclawed.config.WorkerTemplate`.

    Pass an existing ``WorkerTemplate`` to edit it, or ``None`` to create a new one.
    Returns the saved ``WorkerTemplate`` on success, or ``None`` on cancel.
    """

    DEFAULT_CSS = """
    WorkerTemplateModal {
        align: center middle;
    }
    WorkerTemplateModal > #wtm-dialog {
        width: 72;
        height: auto;
        max-height: 40;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    WorkerTemplateModal #wtm-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    WorkerTemplateModal .wtm-row {
        width: 100%;
        height: 3;
    }
    WorkerTemplateModal .wtm-label {
        width: 18;
        padding: 1 1 0 0;
    }
    WorkerTemplateModal .wtm-label-top {
        width: 100%;
        color: $text-muted;
        margin-top: 1;
        height: 1;
    }
    WorkerTemplateModal .wtm-input {
        width: 1fr;
    }
    WorkerTemplateModal .wtm-select {
        width: 1fr;
    }
    WorkerTemplateModal #ta-wtm-prompt {
        height: 7;
        margin-bottom: 1;
    }
    WorkerTemplateModal #wtm-error {
        width: 100%;
        color: $error;
        height: 1;
        margin-bottom: 0;
    }
    WorkerTemplateModal #wtm-buttons {
        width: 100%;
        height: 3;
        align-horizontal: right;
        margin-top: 1;
    }
    WorkerTemplateModal #wtm-buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    _MODEL_OPTIONS = [
        ("sonnet", "sonnet"),
        ("opus", "opus"),
        ("haiku", "haiku"),
    ]
    _PERM_OPTIONS = [
        ("default", "default"),
        ("acceptEdits", "acceptEdits"),
        ("bypassPermissions", "bypassPermissions"),
    ]

    def __init__(self, template: WorkerTemplate | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._template = template  # None → creating new

    def compose(self) -> ComposeResult:
        is_new = self._template is None
        title = "New Worker Template" if is_new else f"Edit Template: {self._template.name}"  # type: ignore[union-attr]
        model_val = self._template.model if self._template else "sonnet"
        perm_val = self._template.permission_mode if self._template else "bypassPermissions"
        name_val = self._template.name if self._template else ""
        prompt_val = self._template.system_prompt if self._template else ""
        tools_val = (self._template.allowed_tools or "") if self._template else ""

        with Vertical(id="wtm-dialog"):
            yield Label(title, id="wtm-title")
            with Horizontal(classes="wtm-row"):
                yield Label("Name", classes="wtm-label")
                yield Input(value=name_val, placeholder="e.g. Security Auditor", id="inp-wtm-name", classes="wtm-input")
            yield Label("System Prompt", classes="wtm-label-top")
            yield TextArea(prompt_val, id="ta-wtm-prompt")
            with Horizontal(classes="wtm-row"):
                yield Label("Model", classes="wtm-label")
                yield Select(self._MODEL_OPTIONS, value=model_val, id="sel-wtm-model", classes="wtm-select", allow_blank=False)
            with Horizontal(classes="wtm-row"):
                yield Label("Permission Mode", classes="wtm-label")
                yield Select(self._PERM_OPTIONS, value=perm_val, id="sel-wtm-perm", classes="wtm-select", allow_blank=False)
            with Horizontal(classes="wtm-row"):
                yield Label("Allowed Tools", classes="wtm-label")
                yield Input(
                    value=tools_val,
                    placeholder="(inherit global, e.g. Read,Edit,Bash)",
                    id="inp-wtm-tools",
                    classes="wtm-input",
                )
            yield Label("", id="wtm-error")
            with Horizontal(id="wtm-buttons"):
                yield Button("Save", id="btn-wtm-save", variant="primary")
                yield Button("Cancel", id="btn-wtm-cancel")

    def on_mount(self) -> None:
        self.query_one("#inp-wtm-name", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-wtm-save":
            self._do_save()
        elif event.button.id == "btn-wtm-cancel":
            self.dismiss(None)

    def _do_save(self) -> None:
        name = self.query_one("#inp-wtm-name", Input).value.strip()
        if not name:
            self._set_error("Name is required")
            return

        prompt = self.query_one("#ta-wtm-prompt", TextArea).text.strip()
        if not prompt:
            self._set_error("System prompt is required")
            return

        try:
            model_sel = self.query_one("#sel-wtm-model", Select)
            model = str(model_sel.value) if model_sel.value and model_sel.value != Select.BLANK else "sonnet"
        except Exception:
            model = "sonnet"

        try:
            perm_sel = self.query_one("#sel-wtm-perm", Select)
            perm = str(perm_sel.value) if perm_sel.value and perm_sel.value != Select.BLANK else "bypassPermissions"
        except Exception:
            perm = "bypassPermissions"

        tools_raw = self.query_one("#inp-wtm-tools", Input).value.strip()
        tools: str | None = tools_raw if tools_raw else None

        # Preserve ID when editing, generate a new one when creating
        if self._template is not None:
            tmpl_id = self._template.id
        else:
            # Slug from name + short uuid for uniqueness
            slug = "-".join(name.lower().split())[:24]
            tmpl_id = f"{slug}-{uuid.uuid4().hex[:6]}"

        self.dismiss(WorkerTemplate(
            id=tmpl_id,
            name=name,
            system_prompt=prompt,
            model=model,
            permission_mode=perm,
            allowed_tools=tools,
            builtin=False,
        ))

    def _set_error(self, msg: str) -> None:
        try:
            self.query_one("#wtm-error", Label).update(msg)
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)


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
