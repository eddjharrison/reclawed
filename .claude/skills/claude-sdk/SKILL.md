---
name: claude-sdk
description: >
  Claude Agent SDK integration for Re:Clawed. Covers ClaudeSDKClient,
  streaming events, tool approval callbacks, permission modes, and
  session lifecycle management.
license: MIT
compatibility: Designed for Claude Code
allowed-tools: Read Grep Glob Bash
user-invocable: false
metadata:
  version: "1.0.0"
  category: "domain"
  status: "active"
  updated: "2026-03-17"
  tags: "claude, sdk, agent, streaming, tools, permissions"

triggers:
  keywords: ["Claude SDK", "Agent SDK", "ClaudeSDKClient", "can_use_tool", "PermissionResult", "streaming", "tool approval"]
  languages: ["python"]
---

# Claude Agent SDK Integration — Re:Clawed

How Re:Clawed interfaces with Claude Code via the Agent SDK.

## Quick Reference

### Session Lifecycle

1. **Create** — `ClaudeAgentOptions(model, permission_mode, allowed_tools, cwd)`
2. **Stream** — async iteration over SDK events (text, tool_use, tool_result)
3. **Tool Approval** — `can_use_tool` callback bridges to TUI approval UI
4. **Restart** — silent restart on permission mode change (no "Initializing" flash)

### Permission Modes (F5 cycle)

```python
PERMISSION_MODES = ["default", "plan", "acceptEdits", "bypassPermissions"]
```

- `default` — ask for approval on dangerous tools
- `plan` — read-only, Claude can only suggest changes
- `acceptEdits` — auto-approve edits, ask for bash
- `bypassPermissions` — auto-approve everything (⚠️ shown in red on status bar)

### Tool Resolution

Workspace-level overrides take priority:
```python
def _effective_allowed_tools(self) -> list[str]:
    ws = self._current_workspace()
    if ws and ws.allowed_tools:
        return ws.allowed_tools.split(",")
    return self.config.allowed_tools.split(",")
```

### Streaming Events

| Event Type | Handling |
|------------|----------|
| `StreamText` | Append to message bubble, auto-scroll |
| `StreamToolUse` | Show tool activity inline (Reading, Editing...) |
| `StreamToolResult` | Collapsible tool output |
| `AskUserQuestion` | Multi-question form widget |
| Choice detection | ChoiceButtons auto-submit |

### AskUserQuestion Tool Structure

```json
{
  "questions": [{
    "question": "Which option?",
    "header": "Selection",
    "options": [{"label": "Option A", "description": "..."}],
    "multiSelect": false
  }]
```

**Critical**: In `bypassPermissions` mode, the `can_use_tool` callback does NOT fire.
Intercept AskUserQuestion at the `StreamToolUse` event level instead.

### Auto-Naming Sessions

Uses haiku model via subprocess (not SDK) for lightweight naming:
```python
env = {**os.environ, "NO_COLOR": "1"}
proc = subprocess.Popen(
    ["claude", "--model", "haiku", "--output-format", "text", "-p", prompt],
    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    env=env,
)
```

### Key Files

| File | Purpose |
|------|---------|
| `src/reclawed/claude_session.py` | ClaudeSDKClient wrapper |
| `src/reclawed/claude.py` | Subprocess-based fallback |
| `src/reclawed/screens/chat.py` | Stream event handling |
