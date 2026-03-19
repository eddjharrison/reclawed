# Re:Clawed

A WhatsApp-style TUI for the Claude CLI. Persistent sessions, workspaces, encrypted group chats, session import — all on top of your existing Claude Code subscription. No API key needed.

![Re:Clawed Screenshot](screenshot.png)

## Install

**Requires the `claude` CLI** — [install Claude Code](https://claude.ai/code) first.

```bash
git clone git@github.com:eddjharrison/reclawed.git
cd reclawed
python3.12 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
```

**Optional — group chat tunneling** (lets remote participants join without port forwarding):

```bash
brew install cloudflared                    # macOS
winget install cloudflare.cloudflared       # Windows
sudo apt install cloudflared                # Debian/Ubuntu
```

## Quick Start

```bash
reclawed                  # open most recent session (or new chat)
reclawed --continue       # resume last session explicitly
reclawed --session <id>   # resume a specific session by ID
```

## Features

### Chat
- **Persistent Claude sessions** — powered by the Agent SDK. Full conversation memory across app restarts
- **Concurrent sessions** — multiple chats stream independently. Background sessions show unread badges
- **Streaming** — token-by-token with live markdown rendering and tok/s counter
- **Message editing** — `e` to edit; Claude re-generates. Shows `[edited]` indicator
- **Message deletion** — `d` to soft-delete a message and its paired reply
- **Reply / Quote** — threaded replies (`r`) with inline preview; quote into compose (`q`)
- **Bookmark / pin** — `b` to pin; `Ctrl+P` opens pinned messages
- **Copy / Search** — `c` copies to clipboard; `/` searches the session
- **Cost tracking** — cumulative session cost in the status bar

### Interactivity
- **Tool activity display** — see what Claude is doing in real-time: "Reading src/foo.py...", "Running: pytest -v", "Editing config.py". Click to expand tool input/output details
- **Tool approval UI** — when Claude needs permission (in `default` or `acceptEdits` mode), approve/deny buttons appear inline in the chat. No more blind auto-approve
- **Question detection** — when Claude asks a clarifying question, the message bubble is highlighted with a visual indicator
- **Choice selection** — when Claude presents numbered options (1., 2., 3.), clickable buttons appear below the message. Click to auto-fill your response

### Workspaces
- **Multi-project management** — group sessions by project directory. Each workspace points Claude at the right codebase
- **Sidebar sections** — collapsible workspace groups with `+ New Chat` per workspace
- **Session import** — auto-discover projects from `~/.claude/projects/`, import last 20 sessions per project with one click
- **Settings screen** (`F4` or command palette) — toggle workspaces, add manual paths, import sessions
- **Config persistence** — workspaces saved to `config.toml` and survive app restarts
- **cwd passthrough** — Claude operates in the correct directory per workspace

```toml
[[workspaces]]
name = "Frontend"
path = "~/projects/frontend"

[[workspaces]]
name = "Backend"
path = "~/projects/backend"
```

### Session Management
- **Searchable sidebar** — filter sessions by name; toggle with `Ctrl+S`
- **Inline rename** — `m` in the sidebar context menu
- **Context menu** — archive, mute/unmute, delete, mark-unread
- **Auto-naming** — sessions named from the first message
- **Export** — `Ctrl+E` dumps to `~/Desktop/<name>.md`
- **Change display name** — via command palette

### Group Chat
- **Persistent relay daemon** — group chats survive app restarts, reboots, and run for weeks. Messages buffer in SQLite while you're offline and replay on reconnect
- **Two deployment modes**:
  - **Local mode** (default): daemon auto-managed on your machine + Cloudflare tunnel for remote access
  - **Remote mode**: team relay on a VPS with a stable URL — just configure and go
- **Session-aware fork** — your Claude's full conversation history is carried into the group room
- **E2E encryption** — AES-256-GCM with PBKDF2-derived room keys. Relay server never sees plaintext
- **Background receiving** — switch to another chat; group messages still arrive, store in DB, show unread badges
- **Typing indicators** — "Alice is typing..." with debounce and auto-expire
- **Read receipts** — sent/read delivery status on outgoing messages
- **Invite to chat** (`Ctrl+I`) — upgrade any 1:1 session into a group mid-conversation. Claude keeps full context
- **@mention routing** — `@Ed's Claude` or `@Ed` to direct messages
- **Room modes** (`F3`) — per-room, synchronized across all participants:
  - **Humans Only** — no Claude unless @mentioned
  - **Claude Assists** — Claude responds to your messages only
  - **Full Auto** — all Claudes respond to all human messages
  - **C2C** — Claudes work autonomously, responding to each other
- **Shared context** — optionally prepend recent group messages as Claude context
- **Mid-chat permission switching** (`F5`) — cycle default / acceptEdits / bypassPermissions without losing context. Status bar shows current mode. Combine C2C + bypass for autonomous overnight work
- **Auto-reconnect** — exponential backoff with `sync_response` replay of missed messages

### Orchestrator / Worker Sessions
- **Orchestrator mode** (`F7`) — promotes a session so Claude can plan and delegate work to parallel workers
- **Worker spawning** — Claude proposes `{{WORKER task="..." model="..." permissions="..."}}` tags; you see Spawn All / Skip buttons. Or right-click to spawn manually
- **Autonomous sprints** — in `bypassPermissions` mode, workers auto-spawn without approval. Workers complete, orchestrator auto-responds, spawns follow-up tasks
- **Sidebar nesting** — workers appear indented under their orchestrator with status icons (`⟳` running, `✓` complete). Completed workers collapsible via clickable toggle
- **Auto-summary** — Haiku generates a 2-3 sentence summary when workers finish; injected as a notification into the orchestrator chat
- **Debounced response loop** — when multiple workers finish close together, the orchestrator waits 3 seconds then responds once with the full picture
- **Concurrent stream protection** — per-session lock prevents two simultaneous SDK calls from corrupting state
- **Worker templates** — preconfigure worker types (implementation, test-writer, code-reviewer) in `config.toml` with model, permissions, and system prompts
- **Lifecycle management** — cap of 10 concurrent workers (completed don't count); bulk archive completed workers from context menu

### Encryption
- **E2E relay encryption** — AES-256-GCM before messages leave your machine. Key derived from passphrase via PBKDF2-HMAC-SHA256 (100k iterations, room ID as salt)
- **Local database encryption** — all history encrypted at rest with auto-generated 256-bit key
- **Backward compatible** — plaintext and encrypted messages coexist seamlessly

### Appearance
- **Multi-model** — cycle sonnet / opus / haiku with `F2`; persisted per session
- **Themes** — dark / light / dracula / monokai with `Ctrl+T`
- **Workspace badge** — current workspace shown in status bar
- **Command palette** — Settings, Change Display Name, Import Workspaces

## Group Chat Setup

### Local Mode (default — any number of participants)

1. Press `Ctrl+G` → **Create**
2. Re:Clawed starts a persistent relay daemon on `localhost:8765` with SQLite message buffering
3. If `cloudflared` is installed, a public `wss://` tunnel opens automatically
4. Copy the connection string and share it
5. Press **Start Chat** to enter the room

The daemon **survives TUI restarts**. Quit and reopen — your group chat is still alive. Messages sent while you were offline are replayed on reconnect.

### Remote Mode (team on a VPS)

**On the server:**
```bash
reclawed-relay --port 8765 --token team-secret --db /var/lib/reclawed/relay.db
```

Or as a systemd service for auto-restart on reboot.

**On each client** (`config.toml`):
```toml
relay_mode = "remote"
relay_url = "wss://relay.company.com"
relay_token = "team-secret"
```

Then `Ctrl+G` → **Create** — the connection string uses the stable company URL. No daemon management needed.

### Joining a Group

1. Press `Ctrl+G` → **Join**
2. Paste the connection string (encryption key is extracted automatically)
3. Press **Join**

### Inviting to an Existing Chat

Already mid-conversation with Claude? Press `Ctrl+I` to upgrade the session into a group. Your Claude keeps full context — no fresh start. Share the connection string and others can join.

### How Group Chat Works

Each participant runs their **own Claude locally on their own machine**. The relay server is just an encrypted message pipe — it routes text between participants but never sees plaintext.

**Isolation model:**

| | Alice's Claude | Bob's Claude |
|---|---|---|
| **Runs on** | Alice's machine | Bob's machine |
| **Can access** | Alice's files only | Bob's files only |
| **Permissions** | Alice's config | Bob's config |
| **Sees from others** | Message text only | Message text only |

When Alice types `@Bob's Claude can you run the tests?`, that message travels through the encrypted relay to Bob's machine. Bob's Claude reads it, runs `pytest` on **Bob's machine**, and sends the results back as a message. Alice never gets filesystem access to Bob's machine, and Bob's Claude never touches Alice's files.

**Context and forking:**
- When you create a group or invite someone (`Ctrl+I`), **your** Claude carries your full prior conversation context into the room via session forking
- Other participants' Claudes start fresh in the group (or carry their own context if they were mid-conversation)
- No participant can see another's Claude session history or tool usage from before the group started

**Think of it as a group chat where everyone brought their own assistant.** The assistants can talk to each other and collaborate, but each one only has access to their own owner's workspace.

### Scaling

The relay server handles any number of participants and rooms. Practical considerations:

- **2-5 people** — ideal for pair programming, small team collaboration
- **5-10 people** — works well in "Humans Only" or "Claude Assists" mode to control response volume
- **10+ people** — use "Humans Only" mode and a VPS relay; the bottleneck is Claude response volume, not the relay infrastructure

In "Full Auto" or "C2C" mode, every participant's Claude generates responses — costs and noise scale linearly with participant count.

## Keybindings

**Always available** (work even while typing):

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line |
| `Ctrl+N` | New chat (in current workspace) |
| `Ctrl+S` | Toggle sidebar |
| `Ctrl+G` | Group chat (Create / Join) |
| `Ctrl+I` | Invite to group chat |
| `Ctrl+T` | Cycle theme |
| `Ctrl+E` | Export to markdown |
| `Ctrl+P` | Pinned messages |
| `F2` | Cycle model |
| `F3` | Cycle room mode (Humans Only / Claude Assists / Full Auto / C2C) |
| `F4` | Settings / Import |
| `F5` | Cycle permissions (default / acceptEdits / bypassPermissions) |
| `F7` | Toggle orchestrator mode |
| `Ctrl+D` | Quit |

**Navigate mode** (`Tab` to enter, `Esc` to return):

| Key | Action |
|-----|--------|
| `Up` / `Down` | Select messages |
| `r` | Reply |
| `e` | Edit |
| `d` | Delete |
| `q` | Quote into compose |
| `b` | Bookmark / pin |
| `c` | Copy |
| `/` | Search |
| `?` | Help |

## Configuration

Config file location:
- **macOS**: `~/Library/Application Support/reclawed/config.toml`
- **Linux**: `~/.config/reclawed/config.toml`
- **Windows**: `%APPDATA%\reclawed\config.toml`

```toml
# Display & UI
theme = "dark"                    # dark | light | dracula | monokai
participant_name = "User"         # your name in group chats
stream_throttle_ms = 50

# Claude
claude_binary = "claude"
permission_mode = "acceptEdits"   # default | acceptEdits | bypassPermissions
allowed_tools = "Read,Edit,Bash,Glob,Grep,Write"

# Relay (group chat)
relay_mode = "local"              # local (auto-daemon) | remote (external server)
relay_port = 8765                 # port for local daemon
# relay_url = "wss://relay.company.com"   # remote mode only
# relay_token = "team-secret"             # remote mode only

# Group chat behavior
group_auto_respond = "claude_assists"  # humans_only | claude_assists | full_auto | claude_to_claude
group_context_mode = "isolated"   # isolated | shared_history
group_context_window = 20

# Workspaces (add as many as you like)
[[workspaces]]
name = "Frontend"
path = "~/projects/frontend"

[[workspaces]]
name = "Backend"
path = "~/projects/backend"
```

## Security

**Local encryption**: Auto-generated 256-bit AES key at `{data_dir}/local.key`. All message content encrypted at rest in SQLite.

**Group chat encryption**: AES-256-GCM with PBKDF2-derived room key (100k iterations, room ID as salt). Passphrase embedded in connection string. Relay server only sees ciphertext.

**Relay auth**: Token-based access control, separate from encryption. The relay server is encryption-agnostic.

If `local.key` is lost, locally encrypted messages become unreadable. Back it up.

## Stack

- **claude-agent-sdk** — persistent sessions with memory, resume, and fork
- **textual** — TUI framework
- **cryptography** — AES-256-GCM, PBKDF2
- **websockets** — relay server + client
- **click** — CLI
- **SQLite** — message, session, and relay persistence
- **cloudflared** (optional) — NAT traversal

## Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v -k "not relay"       # fast suite (~230 tests)
python -m pytest tests/ -v                        # full suite including relay
python -m pytest tests/ -v -m slow                # daemon integration tests
```
