# Re:Clawed

A WhatsApp-style TUI for the Claude CLI. Reply to messages, quote, bookmark, and manage sessions — all on top of your existing Claude Code subscription. No API key needed.

![Re:Clawed Screenshot](screenshot.png)

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

**Always available** (work even while typing):

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line |
| `Ctrl+N` | New chat |
| `Ctrl+S` | Session picker |
| `Ctrl+T` | Cycle theme (dark/light/dracula/monokai) |
| `Ctrl+E` | Export session to markdown |
| `Ctrl+P` | View pinned messages |
| `F2` | Cycle model (sonnet/opus/haiku) |
| `Ctrl+D` / `Ctrl+C` | Quit |

**Navigate mode** (press `Tab` to toggle):

| Key | Action |
|-----|--------|
| `Up/Down` | Select messages |
| `r` | Reply to selected message |
| `q` | Quote selected into compose |
| `b` | Bookmark/pin toggle |
| `c` | Copy to clipboard |
| `/` | Search messages |
| `Esc` | Deselect / back to typing |
| `?` | Help |

## How it works

Re:Clawed wraps the `claude` CLI as a subprocess, streaming responses in real-time via `--output-format stream-json`. Conversations persist in a local SQLite database with full reply chain tracking. Session continuity is maintained through Claude's `--session-id` flag.

## Stack

- **textual** — TUI framework
- **rich** — markdown rendering
- **click** — CLI
- **SQLite** — message & session persistence
