# Re:Clawed

WhatsApp-style TUI wrapping the `claude` CLI via the Agent SDK. Python 3.12 + Textual + claude-agent-sdk + websockets + cryptography + SQLite.

## Development Workflow

- **Virtual env always**: `source .venv/bin/activate` before running or testing anything
- **Branch convention**: commit to `master` for small fixes. For larger features, use a feature branch and PR back to `master`
- **Test before commit**: run `python -m pytest tests/ -v -k "not relay"` before committing. Run the full suite (`python -m pytest tests/ -v`) when touching relay or crypto code
- **Commit style**: imperative prefix — `Fix ...`, `Add ...`, `Update ...`. One logical change per commit. Message describes the *why*, not just the *what*

## Feature Development Process

1. **Plan first** — for non-trivial features, enter plan mode and outline the approach before writing code. Get alignment before implementation
2. **Implement incrementally** — small, working steps. Don't rewrite entire files when a targeted edit will do
3. **Test alongside** — new features get tests in the same commit. Match the existing `test_{module}.py` per-module pattern
4. **No orphan files** — don't create new modules without wiring them into the architecture. Update imports, `__init__.py`, and any relevant screens/widgets
5. **Don't refactor unless asked** — if it works and wasn't part of the task, leave it alone
6. **Always go for the true architectural solution** — don't take quick wins or band-aids. Design the proper solution even if it requires more work

## Code Conventions

- Textual widgets use `compose()` with `Label` components, not `Static` with Rich markup
- `MessageBubble` must have `height: auto` in CSS (it extends `Vertical` which defaults to `height: 1fr`, clipping content)
- `MessageBubble.finalize_content()` is async — always `await` it (Markdown.update() returns AwaitComplete)
- `priority=True` on all `Ctrl+` key bindings (so they work when TextArea has focus)
- Async throughout — SDK client, relay client/server, all use `asyncio`
- Echo prevention in relay receive loop — skip messages where `sender_id == own participant_id`
- Config loaded via `Config.load()`, never bare `Config()`

## Architecture Rules

- `chat.py` is the main orchestrator — sidebar + chat panel horizontal layout
- `ClaudeSession` (in `claude_session.py`) wraps `ClaudeSDKClient` — one persistent session per chat, pooled in `_claude_sessions` dict so switching chats doesn't kill background work
- `_stream_response` captures its session context at start and only updates the UI if that session is still the active one; store writes always happen regardless
- `@work(thread=False)` on `_stream_response` (NOT `exclusive=True`) so multiple sessions can stream concurrently
- Session resume uses the SDK's `resume=session_id` — reliable context retention across app restarts
- Group chat fork uses `fork_session=True` to carry full conversation context into the group room
- SDK environment guard: `env={"CLAUDECODE": ""}` in options to allow running inside Claude Code
- Model name comes from `AssistantMessage.model`, NOT from the `usage` dict keys

### Relay Architecture

- **Relay daemon** runs as a persistent background subprocess (`relay/daemon.py`), NOT embedded in the TUI. Survives TUI quit/restart.
- **Two modes**: `relay_mode = "local"` (TUI auto-manages daemon) or `relay_mode = "remote"` (external VPS server)
- **Daemon info** stored in `{data_dir}/relay_daemon.json` — PID, port, token. Reused across TUI restarts.
- **Relay connections are pooled** in `_relay_clients` dict (like `_claude_sessions`) — switching sessions detaches the active pointer but doesn't disconnect. Background receive loops continue.
- `_relay_receive_loop(session_id)` is session-aware — uses `_is_active()` closure to decide UI vs background storage
- `_handle_sync_response` unpacks missed messages from server replay on reconnection
- Dedup via `_seen_message_ids` set on `RelayClient` — prevents duplicate messages from sync_response
- `_make_relay_status_callback(session_id)` returns a session-bound closure so background relays don't touch the status bar
- `_stream_response` captures `stream_relay` at start to prevent broadcasting to wrong room on session switch
- On startup, ALL group sessions are reconnected (not just the active one)
- Relay protocol changes must consider cross-platform compatibility (tested on macOS + Windows)
- Session token auth is required for relay connections — both creator and joiner must pass it
- Cloudflare tunnel URL parsed from stderr via `readline`, not chunk reads

### Encryption

- Encryption is layered: `crypto.py` has all primitives, `relay/client.py` encrypts/decrypts at the wire boundary, `store.py` encrypts/decrypts at the DB boundary
- The relay server is encryption-agnostic — it routes opaque JSON payloads and never sees plaintext
- Room encryption keys are derived from a passphrase via PBKDF2 (not from the relay auth token)
- Local encryption key is a random 32-byte file at `{data_dir}/local.key` — loaded once at app startup

### Room Modes & Permissions

- Room modes are **per-room and synchronized** via `room_mode` relay message type — all participants see the same mode
- Four modes: `humans_only`, `claude_assists`, `full_auto`, `claude_to_claude`
- Mode persisted on `Session.room_mode` — survives app restart and session switch
- Server stores mode in `_room_modes` dict and includes it in presence updates for new joiners
- Permission mode (`F5`) is **per-session** — each participant controls their own Claude's permissions independently
- Permission switch works by stopping the `ClaudeSession`, removing it from pool, and creating a new one with `resume=session_id` + new `permission_mode`. Full context preserved.
- `Session.permission_mode` persisted in DB — restored on switch and restart
- Read receipts use `_pending_echo_ids` queue to map outgoing local message IDs to relay seq numbers via echo capture

### Interactivity

- `ClaudeSession` yields `StreamToolUse` and `StreamToolResult` events from `ToolUseBlock`/`ToolResultBlock` in `AssistantMessage.content`
- `ToolActivityWidget` renders inline in `MessageBubble` — human-readable tool summaries with collapsible details
- `MessageBubble.add_tool_use()` and `complete_tool()` manage the tool widget lifecycle
- Tool approval uses SDK's `can_use_tool` callback → `asyncio.Future` bridge to TUI → `ToolApprovalWidget` with Approve/Deny buttons
- `_pending_approvals` dict tracks `{tool_use_id: Future}` — resolved when user clicks
- In `bypassPermissions` mode, `can_use_tool` is not set — SDK auto-approves
- `detect_question()` in `utils.py` — heuristic: last paragraph ends with `?` outside code blocks
- `detect_choices()` in `utils.py` — regex for `^\d+\.\s+` patterns, minimum 2 matches
- `ChoiceButtons` widget renders clickable options, posts `Selected` message → fills compose area
- Question detection adds `.has-question` CSS class to bubble (warning border)

### Workspaces

- `Session.cwd` links sessions to project directories
- `Config.workspaces` parsed from `[[workspaces]]` TOML array
- Sidebar groups sessions by workspace when workspaces are configured; flat list otherwise
- `workspace_for_cwd()` resolves workspace name from session cwd
- Session importer (`importer.py`) discovers Claude Code projects from `~/.claude/projects/`, parses JSONL transcripts, creates sessions with `claude_session_id` for SDK resume

## What NOT to Do

- Don't add dependencies to `pyproject.toml` without discussing first
- Don't mock SQLite in store tests — use real in-memory SQLite
- Don't use `Ctrl+M` for bindings (same byte as Enter in terminals)
- Don't use `Static` with Rich markup in widgets (it doesn't render — this was already debugged)
- Don't reuse the relay auth token as an encryption key (it appears in URLs, logs, query strings)
- Don't use `exclusive=True` on `_stream_response` — it kills concurrent session streams
- Don't destroy ClaudeSession on session switch — pool them so background work continues
- Don't destroy RelayClient on session switch — pool them so background messages are received
- Don't parse model name from `ResultMessage.usage` keys (they're token field names, not model names)
- Don't auto-commit or push without being asked
- Don't use `asyncio.to_thread` for Store operations — SQLite connections are single-threaded
- Don't stop the relay daemon on TUI quit — it persists for other sessions

## Testing

- Test files: `tests/test_{module}.py`
- Shared fixtures in `tests/conftest.py`
- `asyncio_mode = "auto"` in pyproject.toml — no need for `@pytest.mark.asyncio` decorators
- Relay integration tests are slow — run separately with `python -m pytest tests/ -v -k "relay"`
- Daemon integration tests use `@pytest.mark.slow` — run with `-m slow`
- Always run tests from the repo root with the venv activated
- When creating StatusBar instances via `object.__new__()` in tests, include all `_` attributes (including `_encrypted`, `_workspace_name`, `_permission_mode`)
- When mocking ClaudeSession in tests, set `s._ready.set()` before calling `send_message`
