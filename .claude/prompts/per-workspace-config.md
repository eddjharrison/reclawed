# Per-Workspace Config

## Goal
Each workspace can have its own model, permission mode, and allowed tools. When switching to a session in that workspace, the settings automatically apply.

## Implementation Plan

### 1. Config: Add optional fields to Workspace
In `src/reclawed/config.py`:
```toml
[[workspaces]]
name = "Frontend"
path = "~/projects/frontend"
model = "sonnet"
permission_mode = "acceptEdits"
allowed_tools = "Read,Edit,Glob,Grep"
```

- Add `model: str | None = None`, `permission_mode: str | None = None`, `allowed_tools: str | None = None` to Workspace
- None = inherit from global config

### 2. Session creation: Apply workspace config
In `src/reclawed/screens/chat.py`:
- When creating a new session in a workspace, check workspace config
- Override _selected_model and _selected_permission from workspace config
- Pass workspace-specific allowed_tools to ClaudeSession

### 3. Session switching: Restore workspace config
- When switching to a session that belongs to a workspace, apply workspace overrides
- When switching to Default workspace, use global config

### 4. Settings screen: Per-workspace config editing
- In the workspace tab of F4 settings, add model/permission/tools dropdowns per workspace

## Files to Modify
- src/reclawed/config.py (Workspace dataclass, load, save)
- src/reclawed/screens/chat.py (_new_chat_with_cwd, _switch_to_session, _start_claude_session)
- src/reclawed/screens/settings.py (workspace config editing)
- tests/test_config.py
