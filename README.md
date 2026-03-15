# Re:Clawed

A WhatsApp-style TUI for the Claude CLI. Reply to messages, quote, bookmark, and manage sessions — all on top of your existing Claude Code subscription. No API key needed.



## Install

```bash
git clone git@github.com:eddjharrison/reclawed.git
cd reclawed
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```bash
reclawed                  # new chat
reclawed --continue       # resume last session
reclawed --session <id>   # resume specific session
```

## Keybindings

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line |
| `Tab` | Toggle navigate/type mode |
| `Up/Down` | Select messages (navigate mode) |
| `r` | Reply to selected message |
| `q` | Quote selected into compose |
| `b` | Bookmark toggle |
| `c` | Copy to clipboard |
| `/` | Search messages |
| `Ctrl+N` | New chat |
| `Ctrl+S` | Session picker |
| `Esc` | Deselect / cancel reply |

## How it works

Re:Clawed wraps the `claude` CLI as a subprocess, streaming responses in real-time via `--output-format stream-json`. Conversations persist in a local SQLite database with full reply chain tracking. Session continuity is maintained through Claude's `--session-id` flag.

## Stack

- **textual** — TUI framework
- **rich** — markdown rendering
- **click** — CLI
- **SQLite** — message & session persistence
