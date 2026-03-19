"""Read/write Claude Code settings files (hooks + MCP) across all scopes."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

HOOK_EVENTS = [
    "PreToolUse", "PostToolUse", "PostToolUseFailure",
    "UserPromptSubmit", "Stop", "SubagentStop",
    "PreCompact", "PostCompact", "Notification",
    "SubagentStart", "PermissionRequest", "SessionStart",
]


@dataclass
class HookEntry:
    """A single hook command."""
    type: str = "command"
    command: str = ""
    timeout: int | None = None


@dataclass
class HookGroup:
    """A matcher group: optional matcher + list of hooks."""
    matcher: str | None = None
    hooks: list[HookEntry] = field(default_factory=list)


@dataclass
class ScopedHook:
    """A hook group with scope and event metadata for display."""
    event: str
    group: HookGroup
    scope: str  # "project" | "user" | "local"


@dataclass
class McpServerEntry:
    """An MCP server config with scope metadata."""
    name: str
    config: dict
    scope: str  # "project" | "user" | "local"


class ClaudeSettingsManager:
    """Reads/writes Claude Code JSON settings across three scopes."""

    def __init__(
        self,
        project_dir: str | None = None,
        user_settings_dir: Path | None = None,
        user_state_path: Path | None = None,
    ) -> None:
        self._project_dir = Path(project_dir) if project_dir else None
        self._user_settings_dir = user_settings_dir or Path.home() / ".claude"
        self._user_state_path = user_state_path or Path.home() / ".claude.json"

    # --- File paths ---

    def _project_settings_path(self) -> Path | None:
        if self._project_dir is None:
            return None
        return self._project_dir / ".claude" / "settings.json"

    def _local_settings_path(self) -> Path | None:
        if self._project_dir is None:
            return None
        return self._project_dir / ".claude" / "settings.local.json"

    def _user_settings_path(self) -> Path:
        return self._user_settings_dir / "settings.json"

    def _mcp_json_path(self) -> Path | None:
        if self._project_dir is None:
            return None
        return self._project_dir / ".mcp.json"

    # --- JSON I/O ---

    def _read_json(self, path: Path | None) -> dict:
        if path is None or not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Failed to read %s: %s", path, e)
            return {}

    def _write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")
            os.replace(tmp, str(path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # --- Hook parsing ---

    def _parse_hooks(self, data: dict, scope: str) -> list[ScopedHook]:
        hooks_dict = data.get("hooks", {})
        result: list[ScopedHook] = []
        for event, groups in hooks_dict.items():
            if not isinstance(groups, list):
                continue
            for group_data in groups:
                entries = []
                for h in group_data.get("hooks", []):
                    entries.append(HookEntry(
                        type=h.get("type", "command"),
                        command=h.get("command", ""),
                        timeout=h.get("timeout"),
                    ))
                group = HookGroup(
                    matcher=group_data.get("matcher"),
                    hooks=entries,
                )
                result.append(ScopedHook(event=event, group=group, scope=scope))
        return result

    # --- Public API: Hooks ---

    def load_hooks(self) -> list[ScopedHook]:
        """Load hooks from all scopes, merged into a flat list."""
        result: list[ScopedHook] = []
        result.extend(self._parse_hooks(
            self._read_json(self._project_settings_path()), "project"))
        result.extend(self._parse_hooks(
            self._read_json(self._user_settings_path()), "user"))
        result.extend(self._parse_hooks(
            self._read_json(self._local_settings_path()), "local"))
        return result

    def save_hook(self, scope: str, event: str, group: HookGroup) -> None:
        """Add a hook group to the specified scope file."""
        path = self._settings_path_for_scope(scope)
        if path is None:
            raise ValueError(f"Cannot save to scope '{scope}' without project_dir")
        data = self._read_json(path)
        hooks = data.setdefault("hooks", {})
        event_list = hooks.setdefault(event, [])
        group_data: dict = {"hooks": [
            {"type": h.type, "command": h.command, **({"timeout": h.timeout} if h.timeout else {})}
            for h in group.hooks
        ]}
        if group.matcher is not None:
            group_data["matcher"] = group.matcher
        event_list.append(group_data)
        self._write_json(path, data)

    def remove_hook(self, scope: str, event: str, index: int) -> None:
        """Remove a hook group by index from the specified scope file."""
        path = self._settings_path_for_scope(scope)
        if path is None:
            raise ValueError(f"Cannot remove from scope '{scope}' without project_dir")
        data = self._read_json(path)
        hooks = data.get("hooks", {})
        event_list = hooks.get(event, [])
        if 0 <= index < len(event_list):
            event_list.pop(index)
            if not event_list:
                del hooks[event]
            self._write_json(path, data)

    def _settings_path_for_scope(self, scope: str) -> Path | None:
        if scope == "project":
            return self._project_settings_path()
        elif scope == "user":
            return self._user_settings_path()
        elif scope == "local":
            return self._local_settings_path()
        return None

    # --- Public API: MCP Servers ---

    def load_mcp_servers(self) -> list[McpServerEntry]:
        """Load MCP server configs from all scopes, merged."""
        result: list[McpServerEntry] = []
        # Project scope: .mcp.json
        mcp_json = self._read_json(self._mcp_json_path())
        for name, cfg in mcp_json.get("mcpServers", {}).items():
            result.append(McpServerEntry(name=name, config=cfg, scope="project"))
        # User scope: ~/.claude.json top-level mcpServers
        state = self._read_json(self._user_state_path)
        for name, cfg in state.get("mcpServers", {}).items():
            result.append(McpServerEntry(name=name, config=cfg, scope="user"))
        # Local scope: ~/.claude.json projects.{path}.mcpServers
        if self._project_dir:
            proj_key = str(self._project_dir)
            proj_data = state.get("projects", {}).get(proj_key, {})
            for name, cfg in proj_data.get("mcpServers", {}).items():
                result.append(McpServerEntry(name=name, config=cfg, scope="local"))
        return result

    def save_mcp_server(self, scope: str, name: str, config: dict) -> None:
        """Add or update an MCP server in the appropriate file."""
        if scope == "project":
            path = self._mcp_json_path()
            if path is None:
                raise ValueError("Cannot save project-scope MCP without project_dir")
            data = self._read_json(path)
            data.setdefault("mcpServers", {})[name] = config
            self._write_json(path, data)
        elif scope == "user":
            data = self._read_json(self._user_state_path)
            data.setdefault("mcpServers", {})[name] = config
            self._write_json(self._user_state_path, data)
        elif scope == "local":
            if self._project_dir is None:
                raise ValueError("Cannot save local-scope MCP without project_dir")
            data = self._read_json(self._user_state_path)
            proj_key = str(self._project_dir)
            proj = data.setdefault("projects", {}).setdefault(proj_key, {})
            proj.setdefault("mcpServers", {})[name] = config
            self._write_json(self._user_state_path, data)

    def remove_mcp_server(self, scope: str, name: str) -> None:
        """Remove an MCP server from the appropriate file."""
        if scope == "project":
            path = self._mcp_json_path()
            if path is None:
                return
            data = self._read_json(path)
            servers = data.get("mcpServers", {})
            if name in servers:
                del servers[name]
                self._write_json(path, data)
        elif scope == "user":
            data = self._read_json(self._user_state_path)
            servers = data.get("mcpServers", {})
            if name in servers:
                del servers[name]
                self._write_json(self._user_state_path, data)
        elif scope == "local":
            if self._project_dir is None:
                return
            data = self._read_json(self._user_state_path)
            proj_key = str(self._project_dir)
            proj = data.get("projects", {}).get(proj_key, {})
            servers = proj.get("mcpServers", {})
            if name in servers:
                del servers[name]
                self._write_json(self._user_state_path, data)
