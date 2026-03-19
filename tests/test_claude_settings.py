"""Tests for Claude Code settings file I/O."""

import json
from pathlib import Path


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_load_hooks_empty(tmp_path):
    """No settings files → empty hooks list."""
    from reclawed.claude_settings import ClaudeSettingsManager

    mgr = ClaudeSettingsManager(
        project_dir=str(tmp_path),
        user_settings_dir=tmp_path / "user",
        user_state_path=tmp_path / "user" / ".claude.json",
    )
    assert mgr.load_hooks() == []


def test_load_hooks_project_scope(tmp_path):
    """Reads hooks from project .claude/settings.json."""
    from reclawed.claude_settings import ClaudeSettingsManager

    _write_json(tmp_path / ".claude" / "settings.json", {
        "permissions": {"allow": ["Read"]},
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "echo done"}]}],
        },
    })
    mgr = ClaudeSettingsManager(
        project_dir=str(tmp_path),
        user_settings_dir=tmp_path / "user",
        user_state_path=tmp_path / "user" / ".claude.json",
    )
    hooks = mgr.load_hooks()
    assert len(hooks) == 1
    assert hooks[0].event == "Stop"
    assert hooks[0].scope == "project"
    assert hooks[0].group.hooks[0].command == "echo done"


def test_load_hooks_all_scopes(tmp_path):
    """Hooks from all three scopes are merged with correct tags."""
    from reclawed.claude_settings import ClaudeSettingsManager

    # Project scope
    _write_json(tmp_path / ".claude" / "settings.json", {
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo p"}]}]},
    })
    # User scope
    user_dir = tmp_path / "user"
    _write_json(user_dir / "settings.json", {
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo u"}]}]},
    })
    # Local scope
    _write_json(tmp_path / ".claude" / "settings.local.json", {
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo l"}]}]},
    })
    mgr = ClaudeSettingsManager(
        project_dir=str(tmp_path),
        user_settings_dir=user_dir,
        user_state_path=tmp_path / "user" / ".claude.json",
    )
    hooks = mgr.load_hooks()
    scopes = {h.scope for h in hooks}
    events = {h.event for h in hooks}
    assert scopes == {"project", "user", "local"}
    assert events == {"Stop", "PreToolUse", "SessionStart"}


def test_load_hooks_malformed_json(tmp_path):
    """Malformed JSON returns empty, no crash."""
    from reclawed.claude_settings import ClaudeSettingsManager

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text("not json{", encoding="utf-8")
    mgr = ClaudeSettingsManager(
        project_dir=str(tmp_path),
        user_settings_dir=tmp_path / "user",
        user_state_path=tmp_path / "user" / ".claude.json",
    )
    assert mgr.load_hooks() == []


def test_load_mcp_project_scope(tmp_path):
    """Reads MCP servers from .mcp.json."""
    from reclawed.claude_settings import ClaudeSettingsManager

    _write_json(tmp_path / ".mcp.json", {
        "mcpServers": {
            "github": {"command": "gh-mcp", "args": ["serve"]},
        },
    })
    mgr = ClaudeSettingsManager(
        project_dir=str(tmp_path),
        user_settings_dir=tmp_path / "user",
        user_state_path=tmp_path / "user" / ".claude.json",
    )
    servers = mgr.load_mcp_servers()
    assert len(servers) == 1
    assert servers[0].name == "github"
    assert servers[0].scope == "project"
    assert servers[0].config["command"] == "gh-mcp"


def test_load_mcp_all_scopes(tmp_path):
    """MCP servers from all three scopes are merged."""
    from reclawed.claude_settings import ClaudeSettingsManager

    _write_json(tmp_path / ".mcp.json", {
        "mcpServers": {"proj-srv": {"command": "a"}},
    })
    user_state = tmp_path / "user" / ".claude.json"
    _write_json(user_state, {
        "mcpServers": {"user-srv": {"type": "http", "url": "http://x"}},
        "projects": {
            str(tmp_path): {"mcpServers": {"local-srv": {"command": "c"}}},
        },
    })
    mgr = ClaudeSettingsManager(
        project_dir=str(tmp_path),
        user_settings_dir=tmp_path / "user",
        user_state_path=user_state,
    )
    servers = mgr.load_mcp_servers()
    names = {s.name for s in servers}
    scopes = {s.scope for s in servers}
    assert names == {"proj-srv", "user-srv", "local-srv"}
    assert scopes == {"project", "user", "local"}


def test_save_hook_creates_file(tmp_path):
    """save_hook creates settings file if absent."""
    from reclawed.claude_settings import ClaudeSettingsManager, HookGroup, HookEntry

    mgr = ClaudeSettingsManager(
        project_dir=str(tmp_path),
        user_settings_dir=tmp_path / "user",
        user_state_path=tmp_path / "user" / ".claude.json",
    )
    mgr.save_hook("project", "Stop", HookGroup(
        hooks=[HookEntry(command="echo bye")],
    ))
    path = tmp_path / ".claude" / "settings.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "Stop" in data["hooks"]
    assert data["hooks"]["Stop"][0]["hooks"][0]["command"] == "echo bye"


def test_save_hook_preserves_other_keys(tmp_path):
    """save_hook doesn't clobber permissions or other keys."""
    from reclawed.claude_settings import ClaudeSettingsManager, HookGroup, HookEntry

    _write_json(tmp_path / ".claude" / "settings.json", {
        "permissions": {"allow": ["Read"]},
    })
    mgr = ClaudeSettingsManager(
        project_dir=str(tmp_path),
        user_settings_dir=tmp_path / "user",
        user_state_path=tmp_path / "user" / ".claude.json",
    )
    mgr.save_hook("project", "Stop", HookGroup(hooks=[HookEntry(command="echo x")]))
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert data["permissions"]["allow"] == ["Read"]
    assert "Stop" in data["hooks"]


def test_remove_hook(tmp_path):
    """remove_hook removes the correct group by index."""
    from reclawed.claude_settings import ClaudeSettingsManager

    _write_json(tmp_path / ".claude" / "settings.json", {
        "hooks": {
            "Stop": [
                {"hooks": [{"type": "command", "command": "echo first"}]},
                {"hooks": [{"type": "command", "command": "echo second"}]},
            ],
        },
    })
    mgr = ClaudeSettingsManager(
        project_dir=str(tmp_path),
        user_settings_dir=tmp_path / "user",
        user_state_path=tmp_path / "user" / ".claude.json",
    )
    mgr.remove_hook("project", "Stop", 0)
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert len(data["hooks"]["Stop"]) == 1
    assert data["hooks"]["Stop"][0]["hooks"][0]["command"] == "echo second"


def test_save_mcp_server_project(tmp_path):
    """Saves MCP server to .mcp.json."""
    from reclawed.claude_settings import ClaudeSettingsManager

    mgr = ClaudeSettingsManager(
        project_dir=str(tmp_path),
        user_settings_dir=tmp_path / "user",
        user_state_path=tmp_path / "user" / ".claude.json",
    )
    mgr.save_mcp_server("project", "my-srv", {"command": "run-it", "args": []})
    data = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert data["mcpServers"]["my-srv"]["command"] == "run-it"


def test_remove_mcp_server(tmp_path):
    """Removes MCP server from correct file."""
    from reclawed.claude_settings import ClaudeSettingsManager

    _write_json(tmp_path / ".mcp.json", {
        "mcpServers": {"a": {"command": "x"}, "b": {"command": "y"}},
    })
    mgr = ClaudeSettingsManager(
        project_dir=str(tmp_path),
        user_settings_dir=tmp_path / "user",
        user_state_path=tmp_path / "user" / ".claude.json",
    )
    mgr.remove_mcp_server("project", "a")
    data = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert "a" not in data["mcpServers"]
    assert "b" in data["mcpServers"]
