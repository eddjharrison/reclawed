"""Dedicated MCP server management screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from clawdia.claude_settings import ClaudeSettingsManager

# Valid MCP action button prefixes — actions use btn-mcp-{action}-{index}
_MCP_ACTIONS = {"auth", "enable", "disable", "reconnect", "remove"}


class McpManagerScreen(ModalScreen[bool]):
    """Full-screen MCP server management.

    Dismisses with True if any server configuration was changed.
    """

    DEFAULT_CSS = """
    McpManagerScreen {
        align: center middle;
    }
    McpManagerScreen > #mcp-dialog {
        width: 90;
        height: auto;
        max-height: 40;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    McpManagerScreen #mcp-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    McpManagerScreen #mcp-scroll {
        width: 100%;
        height: auto;
        max-height: 30;
    }
    McpManagerScreen .mcp-item {
        width: 100%;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
        border-bottom: solid $primary 20%;
    }
    McpManagerScreen .mcp-header {
        width: 100%;
        height: 1;
    }
    McpManagerScreen .mcp-name {
        width: 24;
        text-style: bold;
    }
    McpManagerScreen .mcp-type {
        width: 16;
        color: $text-muted;
    }
    McpManagerScreen .mcp-status {
        width: 14;
    }
    McpManagerScreen .mcp-scope {
        width: 10;
    }
    McpManagerScreen .scope-project { color: green; }
    McpManagerScreen .scope-user { color: cyan; }
    McpManagerScreen .scope-local { color: yellow; }
    McpManagerScreen .scope-claudeai { color: $primary; }
    McpManagerScreen .scope-managed { color: $text-disabled; }
    McpManagerScreen .status-connected { color: green; }
    McpManagerScreen .status-pending { color: yellow; }
    McpManagerScreen .status-failed { color: red; }
    McpManagerScreen .status-needs-auth { color: yellow; }
    McpManagerScreen .status-disabled { color: $text-disabled; }
    McpManagerScreen .status-unknown { color: $text-disabled; }
    McpManagerScreen .mcp-detail {
        width: 100%;
        height: 1;
        color: $text-muted;
    }
    McpManagerScreen .mcp-tools {
        width: 100%;
        height: 1;
        color: $text-disabled;
    }
    McpManagerScreen .mcp-error {
        width: 100%;
        height: 1;
        color: red;
    }
    McpManagerScreen .mcp-actions {
        width: 100%;
        height: 3;
    }
    McpManagerScreen .mcp-actions Button {
        min-width: 8;
        margin-right: 1;
    }
    McpManagerScreen #mcp-button-bar {
        width: 100%;
        height: 3;
        margin-top: 1;
    }
    McpManagerScreen #mcp-button-bar Button {
        margin-right: 1;
    }
    McpManagerScreen #mcp-status-line {
        width: 100%;
        height: 1;
        color: $success;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
    ]

    def __init__(
        self,
        project_dir: str | None = None,
        claude_session=None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._project_dir = project_dir
        self._claude_session = claude_session
        self._changed = False
        self._server_list: list[dict] = []  # [{name, scope, status, file_entry?}]

    def compose(self) -> ComposeResult:
        with Vertical(id="mcp-dialog"):
            yield Label("MCP Servers", id="mcp-title")
            yield VerticalScroll(id="mcp-scroll")
            yield Label("", id="mcp-status-line")
            with Horizontal(id="mcp-button-bar"):
                yield Button("Add Server", id="btn-add-mcp", variant="primary")
                yield Button("Refresh", id="btn-refresh-mcp")
                yield Button("Close", id="btn-close-mcp")

    def on_mount(self) -> None:
        self.call_later(self._refresh_list_async)

    async def _refresh_list_async(self) -> None:
        await self._refresh_list()

    async def _refresh_list(self) -> None:
        try:
            scroll = self.query_one("#mcp-scroll", VerticalScroll)
        except Exception:
            return
        scroll.remove_children()

        mgr = ClaudeSettingsManager(project_dir=self._project_dir)
        file_servers = {s.name: s for s in mgr.load_mcp_servers()}

        # Get live status from SDK
        sdk_statuses: dict[str, dict] = {}
        if self._claude_session:
            try:
                resp = await self._claude_session.get_mcp_status()
                for srv in resp.get("mcpServers", []):
                    sdk_statuses[srv["name"]] = srv
            except Exception:
                pass

        all_names = sorted(set(file_servers) | set(sdk_statuses))

        if not all_names:
            scroll.mount(Label("No MCP servers configured. Click Add Server to create one."))
            return

        self._server_list = []
        for i, name in enumerate(all_names):
            file_entry = file_servers.get(name)
            sdk_entry = sdk_statuses.get(name)

            cfg = (file_entry.config if file_entry else
                   sdk_entry.get("config", {}) if sdk_entry else {})
            srv_type = cfg.get("type", "stdio")
            status = sdk_entry.get("status", "unknown") if sdk_entry else "unknown"
            scope = file_entry.scope if file_entry else sdk_entry.get("scope", "?") if sdk_entry else "?"

            self._server_list.append({
                "name": name, "scope": scope, "status": status,
                "has_file": file_entry is not None,
            })

            item = Vertical(classes="mcp-item")
            scroll.mount(item)

            header = Horizontal(classes="mcp-header")
            item.mount(header)
            header.mount(Label(name, classes="mcp-name"))
            header.mount(Label(srv_type, classes="mcp-type"))

            status_display = status.replace("-", " ")
            status_lbl = Label(status_display, classes=f"mcp-status status-{status}")
            header.mount(status_lbl)
            header.mount(Label(scope, classes=f"mcp-scope scope-{scope}"))

            if srv_type == "stdio":
                cmd = cfg.get("command", "")
                args = " ".join(cfg.get("args", []))
                detail = f"cmd: {cmd} {args}".strip()
            elif srv_type in ("http", "sse", "claudeai-proxy"):
                detail = f"url: {cfg.get('url', '')}"
            else:
                detail = f"config: {srv_type}"
            if len(detail) > 75:
                detail = detail[:72] + "..."
            item.mount(Label(detail, classes="mcp-detail"))

            if sdk_entry and sdk_entry.get("tools"):
                tool_names = [t.get("name", "?") for t in sdk_entry["tools"]]
                tools_text = ", ".join(tool_names)
                if len(tools_text) > 75:
                    tools_text = tools_text[:72] + "..."
                item.mount(Label(f"tools: {tools_text}", classes="mcp-tools"))

            if sdk_entry and sdk_entry.get("error"):
                item.mount(Label(f"error: {sdk_entry['error']}", classes="mcp-error"))

            actions = Horizontal(classes="mcp-actions")
            item.mount(actions)

            if status == "needs-auth":
                actions.mount(Button("Authenticate", id=f"btn-mcp-auth-{i}", variant="primary"))
            if status in ("connected", "pending"):
                actions.mount(Button("Disable", id=f"btn-mcp-disable-{i}"))
            elif status == "disabled":
                actions.mount(Button("Enable", id=f"btn-mcp-enable-{i}", variant="success"))
            if status == "failed":
                actions.mount(Button("Reconnect", id=f"btn-mcp-reconnect-{i}", variant="warning"))
            if file_entry and scope not in ("managed", "claudeai"):
                actions.mount(Button("Remove", id=f"btn-mcp-remove-{i}"))

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#mcp-status-line", Label).update(text)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-close-mcp":
            self.dismiss(self._changed)
        elif bid == "btn-add-mcp":
            self._add_server()
        elif bid == "btn-refresh-mcp":
            self.call_later(self._refresh_list_async)
        elif bid and bid.startswith("btn-mcp-"):
            self._handle_action(bid)

    def _add_server(self) -> None:
        from clawdia.screens.settings import McpServerEditorScreen

        def on_dismiss(result: "dict | None") -> None:
            if result:
                mgr = ClaudeSettingsManager(project_dir=self._project_dir)
                mgr.save_mcp_server(result["scope"], result["name"], result["config"])
                self._changed = True
                self._set_status(f"Added {result['name']}")
                self.call_later(self._refresh_list_async)

        self.app.push_screen(McpServerEditorScreen(), on_dismiss)

    def _handle_action(self, bid: str) -> None:
        # Parse: btn-mcp-{action}-{index}
        parts = bid.split("-", 3)
        if len(parts) < 4:
            return
        action = parts[2]
        if action not in _MCP_ACTIONS:
            return
        try:
            idx = int(parts[3])
        except ValueError:
            return
        if idx < 0 or idx >= len(self._server_list):
            return
        info = self._server_list[idx]
        name = info["name"]
        scope = info["scope"]

        async def _do() -> None:
            try:
                if action == "auth":
                    if self._claude_session:
                        try:
                            await self._claude_session.toggle_mcp_server(name, True)
                            self._set_status(f"Auth triggered for {name} — check browser")
                        except Exception:
                            self._set_status(
                                f"Auth requires CLI: run 'claude mcp auth' in terminal"
                            )
                    else:
                        self._set_status("No active session")
                elif action == "enable":
                    if self._claude_session:
                        await self._claude_session.toggle_mcp_server(name, True)
                        self._set_status(f"Enabled {name}")
                    else:
                        self._set_status("No active session")
                elif action == "disable":
                    if self._claude_session:
                        await self._claude_session.toggle_mcp_server(name, False)
                        self._set_status(f"Disabled {name}")
                    else:
                        self._set_status("No active session")
                elif action == "reconnect":
                    if self._claude_session:
                        await self._claude_session.reconnect_mcp_server(name)
                        self._set_status(f"Reconnecting {name}...")
                    else:
                        self._set_status("No active session")
                elif action == "remove":
                    self._confirm_remove(name, scope)
                    return
                await self._refresh_list()
            except Exception as e:
                self._set_status(f"Error: {e}")

        self.call_later(_do)

    def _confirm_remove(self, name: str, scope: str) -> None:
        from clawdia.widgets.confirm_screen import ConfirmScreen

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                mgr = ClaudeSettingsManager(project_dir=self._project_dir)
                mgr.remove_mcp_server(scope, name)
                self._changed = True
                self._set_status(f"Removed {name}")
                self.call_later(self._refresh_list_async)

        self.app.push_screen(
            ConfirmScreen(title=f"Remove {name}?", message=f"Remove from {scope} scope"),
            on_confirm,
        )

    def action_close(self) -> None:
        self.dismiss(self._changed)
