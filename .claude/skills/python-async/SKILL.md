---
name: python-async
description: >
  Python 3.11+ async patterns for Re:Clawed. Covers asyncio event loops,
  subprocess management, background tasks, WebSocket connections, and
  Windows-specific async quirks.
license: MIT
compatibility: Designed for Claude Code
allowed-tools: Read Grep Glob Bash
user-invocable: false
metadata:
  version: "1.0.0"
  category: "language"
  status: "active"
  updated: "2026-03-17"
  tags: "python, asyncio, subprocess, windows, background-tasks"

triggers:
  keywords: ["asyncio", "async", "await", "subprocess", "Popen", "background task", "event loop", "Future"]
  languages: ["python"]
---

# Python Async Patterns — Re:Clawed

Async programming patterns used throughout the Re:Clawed codebase.

## Quick Reference

### Subprocess Management (Windows)

Re:Clawed monkey-patches `subprocess.Popen.__init__` at import time to add `CREATE_NO_WINDOW`:
```python
# In src/reclawed/__init__.py — runs before ALL other imports
if sys.platform == "win32":
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | 0x08000000
```

**Critical**: Never use `DETACHED_PROCESS` (0x00000008) — it opens a console window on Windows.
Use `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` for background daemons.

### Background Task Pattern

```python
async def _background_work(self) -> None:
    """Run in background via asyncio.create_task()."""
    try:
        result = await asyncio.to_thread(blocking_function, args)
        # Post result back to Textual via call_from_thread or worker
    except Exception:
        pass  # Background tasks should never crash the TUI

# Launch from a Textual widget/screen:
self._task = asyncio.create_task(self._background_work())
```

### Subprocess with No ANSI Leakage

For processes that might emit ANSI codes (like Claude CLI):
```python
env = {**os.environ, "NO_COLOR": "1"}
proc = await asyncio.create_subprocess_exec(
    "claude", "--output-format", "text",
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    env=env,
)
stdout, _ = await proc.communicate()
```

### asyncio.Future for Tool Approval

Bridge between Claude SDK callbacks and Textual's async event loop:
```python
# In can_use_tool callback (runs in SDK thread):
future = asyncio.Future()
app.call_from_thread(lambda: show_approval_ui(future))
result = await future  # blocks SDK thread until TUI user responds

# In TUI approval handler:
future.set_result(PermissionResultAllow())
```

### Windows Async Pitfalls

1. **ResourceWarning on exit** — suppress with `warnings.filterwarnings("ignore", category=ResourceWarning)`
2. **stderr tracebacks on Ctrl+C** — redirect stderr to devnull on exit: `sys.stderr = open(os.devnull, "w")`
3. **Event loop policy** — Windows uses `ProactorEventLoop` by default (good for subprocess)
4. **Pipe broken errors** — catch `BrokenPipeError` and `ConnectionResetError` in relay connections

### Key Files

| File | Async Pattern |
|------|--------------|
| `src/reclawed/claude_session.py` | Agent SDK async streaming |
| `src/reclawed/claude.py` | Subprocess-based Claude CLI |
| `src/reclawed/relay/client.py` | WebSocket async connections |
| `src/reclawed/relay/daemon.py` | Background daemon management |
| `src/reclawed/cli.py` | Entry point, exit cleanup |
