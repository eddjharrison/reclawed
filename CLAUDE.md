# Re:Clawed

WhatsApp-style TUI wrapping the `claude` CLI. Python 3.12 + Textual + websockets + cryptography + SQLite.

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

## Code Conventions

- Textual widgets use `compose()` with `Label` components, not `Static` with Rich markup
- `MessageBubble` must have `height: auto` in CSS (it extends `Vertical` which defaults to `height: 1fr`, clipping content)
- `MessageBubble.finalize_content()` is async — always `await` it (Markdown.update() returns AwaitComplete)
- `priority=True` on all `Ctrl+` key bindings (so they work when TextArea has focus)
- Async throughout — subprocess management, relay client/server, all use `asyncio`
- 16MB buffer on `asyncio.create_subprocess_exec` stdout reads (default 64KB breaks on long responses)
- Echo prevention in relay receive loop — skip messages where `sender_id == own participant_id`
- Config loaded via `Config.load()`, never bare `Config()`

## Architecture Rules

- `chat.py` is the main orchestrator — sidebar + chat panel horizontal layout
- Relay protocol changes must consider cross-platform compatibility (tested on macOS + Windows)
- Session token auth is required for relay connections — both creator and joiner must pass it
- Cloudflare tunnel URL parsed from stderr via `readline`, not chunk reads
- Encryption is layered: `crypto.py` has all primitives, `relay/client.py` encrypts/decrypts at the wire boundary, `store.py` encrypts/decrypts at the DB boundary
- The relay server is encryption-agnostic — it routes opaque JSON payloads and never sees plaintext
- Room encryption keys are derived from a passphrase via PBKDF2 (not from the relay auth token)
- Local encryption key is a random 32-byte file at `{data_dir}/local.key` — loaded once at app startup

## What NOT to Do

- Don't add dependencies to `pyproject.toml` without discussing first
- Don't mock SQLite in store tests — use real in-memory SQLite
- Don't use `Ctrl+M` for bindings (same byte as Enter in terminals)
- Don't use `Static` with Rich markup in widgets (it doesn't render — this was already debugged)
- Don't reuse the relay auth token as an encryption key (it appears in URLs, logs, query strings)
- Don't auto-commit or push without being asked

## Testing

- Test files: `tests/test_{module}.py`
- Shared fixtures in `tests/conftest.py`
- `asyncio_mode = "auto"` in pyproject.toml — no need for `@pytest.mark.asyncio` decorators
- Relay integration tests are slow — run separately with `python -m pytest tests/ -v -k "relay"`
- Always run tests from the repo root with the venv activated
- When creating StatusBar instances via `object.__new__()` in tests, include all `_` attributes (including `_encrypted`)
