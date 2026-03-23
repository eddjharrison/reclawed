<div align="center">

<pre>
    /\_/\
   ( o.o )
    > ^ <
</pre>

# Clawdia

**Chat, Launch & Administer Whole Divisions of Intelligent Agents**

A WhatsApp-style TUI for Claude Code — persistent sessions, encrypted group chat,
orchestrator/worker delegation, and multi-project workspaces. No API key needed.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-246%2B-brightgreen.svg)](tests/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)]()

| Platform | Python | Status |
|----------|--------|--------|
| `macOS (ARM64)` | 3.12+ | Primary |
| `Linux (x86_64)` | 3.12+ | Supported |
| `Windows (x86_64)` | 3.12+ | Supported |

<img width="1503" height="875" alt="Screenshot 2026-03-23 at 23 21 05" src="https://github.com/user-attachments/assets/38455390-ddd7-4633-900c-296a72213100" />

</div>

---

> You're 200 messages deep in a Claude Code session — context, momentum, a shared understanding of the codebase. You close the terminal.
>
> It's gone.

---

## Why It Exists

The Claude Code CLI is stateless at the UX layer. Every terminal session is an island:

| Raw CLI | Clawdia |
|---------|-----------|
| Session context lost on close | Persistent sessions — resume exactly where you left off |
| One conversation at a time | Multiple concurrent sessions across projects, one TUI |
| No collaboration | E2E encrypted group chat — two devs, two Claudes, one room |
| Manual multi-Claude coordination | Orchestrator delegates to workers in parallel, summaries flow back |
| One project at a time | Workspaces — switch between codebases from the sidebar |
| Static permission level | `F5` to change permissions mid-session — let Claude run free overnight |

---

## Features at a Glance

### Chat
| | |
|---|---|
| **Persistent sessions** | Full memory across restarts, powered by Agent SDK |
| **Live streaming** | Token-by-token with markdown rendering + tok/s counter |
| **Concurrent sessions** | Switch between chats; background ones show unread badges |
| **Edit & regenerate** | `e` to edit any message; Claude re-generates from there |
| **Reply / Quote** | Threaded replies (`r`), quote into compose (`q`) |
| **Bookmarks** | Pin messages (`b`), `Ctrl+P` to view pinned |
| **Search** | `/` to search within a session |
| **Cost tracking** | Running session cost in the status bar |
| **Export** | `Ctrl+E` to markdown on your Desktop |

### Workspaces
| | |
|---|---|
| **Multi-project** | Each workspace points Claude at the right codebase |
| **Session import** | Auto-discover from `~/.claude/projects/` with one click |
| **Color-coded badges** | Auto-assigned colors per workspace in the status bar |
| **Per-workspace config** | Different model, permissions, tools per project |
| **Resizable sidebar** | Drag to resize; width persists across restarts |
| **Session refresh** | Re-import latest sessions from Claude Code any time |

### Group Chat
| | |
|---|---|
| **Persistent relay** | Daemon survives restarts; messages buffer in SQLite offline |
| **E2E encryption** | AES-256-GCM — relay never sees plaintext |
| **Remote relay mode** | Team VPS with stable URL — just configure and go |
| **Invite mid-chat** | `Ctrl+I` upgrades any 1:1 session into a group room — Claude keeps full context, no restart needed |
| **Create or join** | `Ctrl+G` to start a new room or paste a connection string to join an existing one |
| **Typing indicators** | "Alice is typing..." with debounce and auto-expire |
| **Read receipts** | Sent / read delivery status |
| **@mention routing** | Direct messages to specific Claudes or humans |
| **Auto-reconnect** | Exponential backoff — missed messages replayed on reconnect |

### Room Modes (`F3`)
| Mode | What happens |
|------|-------------|
| **Humans Only** | Claude silent unless @mentioned |
| **Claude Assists** | Your Claude responds to your messages |
| **Full Auto** | All Claudes respond to all humans |
| **C2C** | Claudes respond to each other autonomously |

### Orchestrator / Workers
| | |
|---|---|
| **Nested session tree** | Workers shown as children under orchestrator in sidebar |
| **Parallel workers** | Spawn multiple workers simultaneously; each runs independently |
| **Worker templates** | 4 built-in (Implementation Sprint, Test Writer, Code Reviewer, Doc Writer) + create your own from Settings |
| **Custom templates** | Define reusable worker types with tailored system prompts, model, and permission level |
| **Claude-initiated** | Claude proposes worker spawns (with optional `template=`); you approve with one click |
| **Auto-summaries** | Workers report back: commit hashes, changes, edge cases found |
| **Per-worker permissions** | Worker runs `bypassPermissions`; orchestrator stays in `acceptEdits` |

### Interactivity
| | |
|---|---|
| **Tool activity display** | See what Claude is doing in real-time: "Reading src/foo.py...", "Running: pytest -v". Click to expand details |
| **Tool approval UI** | Approve/deny buttons appear inline when Claude needs permission — no blind auto-approve |
| **Clickable file references** | File paths in tool activity are clickable — opens document viewer with syntax highlighting, or diff view for edits |
| **Document viewer** | Full read/edit/diff viewer — syntax highlighting, hunk navigation, unsaved changes warning |
| **Memory browser** | `Ctrl+M` opens Claude's memory files — browse, create, edit, delete |
| **Question detection** | Claude's questions highlighted with accent border |
| **Choice buttons** | Numbered options rendered as clickable buttons |

### Appearance & UX
| | |
|---|---|
| **Model picker** | `F2` cycles sonnet / opus / haiku — persisted per session |
| **Themes** | dark / light / dracula / monokai — `Ctrl+T` |
| **Context gauge** | Battery-style indicator; green to yellow to red as context fills |
| **Mid-session permissions** | `F5` cycles permission mode live — start cautious, switch to `bypassPermissions` when you're ready |
| **Image attachments** | `Alt+V` paste from clipboard, `Alt+A` file picker — cross-platform |

---

## How Group Chat Actually Works

You and a colleague are trying to close out a feature. You've both been using Claude Code all week and have sessions full of context.

You press `Ctrl+G` and create a group room. Clawdia starts a persistent relay daemon in the background and — if you have `cloudflared` installed — opens a public tunnel automatically. You copy the connection string, send it over.

They paste it in with `Ctrl+G` > Join. Done.

Here's what's happening under the hood: each of you has your own Claude, running locally on your own machine, with access only to your own files. The relay in the middle is just an encrypted pipe — it never sees plaintext. Your Claude can read and edit your code. Their Claude can read and edit theirs. Neither touches the other's filesystem.

| | Your Claude | Their Claude |
|---|---|---|
| **Runs on** | Your machine | Their machine |
| **Can access** | Your files only | Their files only |
| **Permissions** | Your config | Their config |
| **Sees from others** | Message text only | Message text only |

You type: `@Alice's Claude can you check if the API changes on your end are compatible with what I've got?`

That message — encrypted — travels through the relay. Their Claude reads it, checks their codebase, and responds in the chat. Everyone sees the answer. Everyone stays in sync.

Switch to **Full Auto** mode with `F3` — now both Claudes respond to all human messages. Hit `F5` to bump permissions to `bypassPermissions`. Flip to **C2C** mode. The humans step back. The Claudes start talking to each other.

Go make coffee. Come back to a thread of 40 messages: one Claude proposed an approach, the other found a flaw, they iterated, agreed on a solution, and opened a PR. The other one's writing the tests.

The relay daemon keeps running after you close Clawdia. Messages buffer in SQLite. Reopen the app, missed messages replay. The group chat is still alive.

For something more permanent, run the relay on a VPS:

```bash
clawdia-relay --port 8765 --token team-secret --db /var/lib/clawdia/relay.db
```

Then set `relay_mode = "remote"` in each client's config and share a stable URL instead of a tunnel.

It's a group chat where everyone brought their own assistant. They can talk to each other, but each one only has access to their own owner's workspace.

---

<details>
<summary><strong>Architecture</strong></summary>

```
                    Textual TUI
  ChatScreen --- Sidebar --- Settings --- Modals
                       |
                 Session Layer
  ClaudeSession (Agent SDK) x N concurrent sessions
  Background streaming - Unread badges - Cost track
           |                         |
   SQLite Store              Relay Infrastructure
  Sessions - Messages       WebSocket daemon/server
  Local AES-256 enc        AES-256-GCM E2E encrypt
  Migrations on init        SQLite message buffer
                            Cloudflare tunnel opt.
```

**Sessions are objects, not processes.** Each `ClaudeSession` is an Agent SDK session instance. Multiple can run concurrently; the event loop streams tokens from all of them. Switching between sessions in the sidebar doesn't kill anything — background sessions keep streaming, badge their unread count, and are immediately available.

**The relay is a message pipe, not a server.** In group chat, each participant's Claude runs locally on their own machine. The relay only routes encrypted ciphertext — it never sees plaintext, has no Claude API access, and has no knowledge of session contents. AES-256-GCM with PBKDF2-derived room keys (100k iterations). The passphrase is embedded in the connection string shared between participants.

**Workers are full sessions, not subagents.** Orchestrator/worker delegation spawns real `ClaudeSession` instances — each gets its own context window, tool set, and permission level. The orchestrator never sees raw diffs from workers; it only receives structured summaries injected on completion. This preserves orchestrator context budget for strategic decisions.

**Tool approval bridges asyncio to the TUI.** When Claude needs permission (in `default` or `acceptEdits` mode), the SDK's `can_use_tool` callback resolves an `asyncio.Future` that the TUI is waiting on. Approve/deny buttons appear inline in the message bubble. No blocking, no modal interruption.

```
src/clawdia/
  screens/       # Textual screens (chat, settings, spawn_worker, group_chat)
  widgets/       # Reusable TUI components (message_bubble, sidebar, resize_handle, ...)
  config.py      # Config dataclass + TOML load/save, WorkerTemplate, BUILTIN_TEMPLATES
  models.py      # Session, Message, Workspace dataclasses
  store.py       # SQLite store with migrations
  utils.py       # Worker proposal parsing, markdown helpers
  relay/         # WebSocket relay server + client + daemon management
```

</details>

---

## Getting Started

**Requires the `claude` CLI** — [install Claude Code](https://claude.ai/code) first.

```bash
git clone git@github.com:eddjharrison/clawdia.git
cd clawdia
python3.12 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
clawdia
```

**Optional — for group chat tunneling** (remote participants without port forwarding):

```bash
brew install cloudflared                    # macOS
winget install cloudflare.cloudflared       # Windows
sudo apt install cloudflared                # Debian/Ubuntu
```

---

## Configuration

Config file location:
- **macOS**: `~/Library/Application Support/clawdia/config.toml`
- **Linux**: `~/.config/clawdia/config.toml`
- **Windows**: `%APPDATA%\clawdia\config.toml`

Everything is also editable from the in-app Settings screen (`F4`).

```toml
# Display & UI
theme = "dark"                    # dark | light | dracula | monokai
participant_name = "You"          # your name in group chats
stream_throttle_ms = 50

# Claude
claude_binary = "claude"
permission_mode = "acceptEdits"   # default | acceptEdits | bypassPermissions
allowed_tools = "Read,Edit,Bash,Glob,Grep,Write"
model = "sonnet"                  # sonnet | opus | haiku

# Relay (group chat)
relay_mode = "local"              # local (auto-daemon) | remote (external server)
relay_port = 8765
# relay_url = "wss://relay.company.com"   # remote mode only
# relay_token = "team-secret"             # remote mode only

# Group chat behaviour
group_auto_respond = "claude_assists"  # humans_only | claude_assists | full_auto | claude_to_claude
group_context_mode = "isolated"        # isolated | shared_history

# Workspaces
[[workspaces]]
name = "Frontend"
path = "~/projects/frontend"
model = "opus"
permission_mode = "bypassPermissions"

# Custom worker templates (4 built-ins always present; add your own here)
[[worker_templates]]
id = "my-template"
name = "My Custom Worker"
system_prompt = "You are a specialist in..."
model = "sonnet"
permission_mode = "bypassPermissions"
```

---

## Keybindings

**Always available:**

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line |
| `Ctrl+N` | New chat |
| `Ctrl+S` | Toggle sidebar |
| `Ctrl+G` | Group chat (Create / Join) |
| `Ctrl+I` | Invite to group |
| `Ctrl+T` | Cycle theme |
| `Ctrl+E` | Export session to Markdown |
| `Ctrl+P` | Pinned messages |
| `F2` | Cycle model (sonnet / opus / haiku) |
| `F3` | Cycle room mode |
| `F4` | Settings |
| `F5` | Cycle permissions |
| `Ctrl+D` | Quit |

**Navigate mode** (`Tab` to enter, `Esc` to exit):

| Key | Action |
|-----|--------|
| `Up` / `Down` | Select messages |
| `r` | Reply |
| `e` | Edit message |
| `d` | Delete message |
| `q` | Quote into compose |
| `b` | Bookmark / pin |
| `c` | Copy to clipboard |
| `/` | Search session |

---

## Security

- `local.key` at `{data_dir}/local.key` encrypts all local message content with AES-256. **Back it up.** Loss is unrecoverable.
- Group relay uses AES-256-GCM E2E encryption — PBKDF2-HMAC-SHA256 (100k iterations, room ID as salt). The relay server only ever routes ciphertext.
- Connection strings embed the room passphrase. Treat them like passwords.
- Relay auth uses token-based access control, separate from the encryption layer.

---

## Stack

| Package | Role |
|---------|------|
| `claude-agent-sdk` | Persistent sessions, resume, fork |
| `textual` | TUI framework |
| `cryptography` | AES-256-GCM, PBKDF2 |
| `websockets` | Relay server + client |
| `click` | CLI entrypoints |
| `SQLite` | Session, message, relay persistence |
| `cloudflared` *(optional)* | NAT traversal for local relay |

---

## Tests

246+ tests across unit, integration, and relay daemon:

```bash
python -m pytest tests/ -v -k "not relay"   # fast suite (~230 tests)
python -m pytest tests/ -v                   # full suite
python -m pytest tests/ -v -m slow          # daemon integration tests
```

Coverage: session management, store/migrations, encryption, relay protocol, worker templates, orchestrator flows, group chat message routing.

---

## Contributing

Areas most open to contribution:
- **Session branching / checkpoints** — SDK fork support is ready; needs TUI layer
- **Sprint tracking** — orchestrator live status panel as workers complete
- **Git diff review mode** — Claude-annotated diff viewer inline in TUI
- **MCP server management** — surface `.claude/settings.json` MCP config in TUI
- **Named Cloudflare tunnels** — stable tunnel URLs surviving daemon restarts

Run the test suite before submitting a PR. New features need tests.

---

*Runs on your existing Claude Code subscription. No API key. No extra cost.*
