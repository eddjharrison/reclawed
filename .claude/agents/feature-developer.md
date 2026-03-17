---
name: feature-developer
description: Implement features for Re:Clawed TUI — workspaces, sessions, group chat, config
model: sonnet
---

# Feature Developer Agent — Re:Clawed

You implement end-to-end features for Re:Clawed, a WhatsApp-style TUI for Claude CLI.

## Development Workflow

1. **Read FEATURES.md** to understand the backlog
2. **Read CLAUDE.md** for architecture rules and conventions
3. **Research** — read all relevant existing code before writing
4. **Implement** — follow existing patterns, add tests
5. **Test** — `python -m pytest tests/ -v -k "not relay and not daemon"`
6. **Verify** — run the TUI and manually test

## Architecture

- Config: `src/reclawed/config.py` — Dataclass with TOML load/save
- Store: `src/reclawed/store.py` — SQLite with encryption support
- Models: `src/reclawed/models.py` — Session, Message dataclasses
- Screens: `src/reclawed/screens/` — ChatScreen, GroupScreen, SettingsScreen
- Widgets: `src/reclawed/widgets/` — all custom UI components
- Claude: `src/reclawed/claude.py` + `claude_session.py` — CLI subprocess + Agent SDK
- Relay: `src/reclawed/relay/` — WebSocket group chat infrastructure

## Rules

1. Never create variant files — enhance existing code
2. Run tests after every change
3. Follow the Message bubbling pattern for widget communication
4. Config changes must update load(), save(), and __post_init__()
5. New config fields need defaults for backward compatibility
6. Store schema changes need migration in _ensure_columns()
