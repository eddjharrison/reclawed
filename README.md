# Re:Clawed

A WhatsApp-style TUI for the Claude CLI. Reply to messages, edit and delete them, run encrypted group chats with typing indicators and read receipts, and manage sessions — all on top of your existing Claude Code subscription. No API key needed.

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
- **Streaming chat** — responses stream token-by-token with live markdown rendering and tok/s counter
- **Message editing** — press `e` on a selected user message to edit; Claude re-generates its response. Edited messages show an `[edited]` indicator
- **Message deletion** — press `d` to soft-delete a message and its paired Claude reply
- **Reply to messages** — threaded replies with inline quote preview; click a reply indicator to jump to the original
- **Quote into compose** — paste a message excerpt directly into your input with `q`
- **Bookmark / pin** — toggle `b` to pin any message; `Ctrl+P` opens the pinned messages view
- **Copy to clipboard** — `c` in navigate mode; uses `pbcopy` (macOS) or `xclip` (Linux)
- **In-session search** — `/` searches all messages in the current session
- **Cost tracking** — cumulative session cost shown in the status bar

### Session Management
- **Session sidebar** — searchable session list with unread badges; toggle with `Ctrl+S`
- **Session rename** — press `m` in the sidebar context menu to rename inline
- **Session management** — right-click any session for archive, mute/unmute, delete, mark-unread
- **Auto-naming** — sessions are automatically named from the first message
- **Session export** — dumps the full conversation to `~/Desktop/<name>.md` with `Ctrl+E`

### Appearance
- **Multi-model switching** — cycle sonnet / opus / haiku with `F2`; persisted per session
- **Theme cycling** — dark / light / dracula / monokai with `Ctrl+T`
- **Relative timestamps** — message times shown as "just now", "5m ago", etc.

### Group Chat
- **Multi-participant rooms** over WebSocket with automatic Cloudflare tunnel
- **E2E encryption** — AES-256-GCM with room-level key derived from a shared passphrase (see below)
- **Typing indicators** — "Alice is typing..." in the status bar with 3s debounce and 5s auto-expire
- **Read receipts** — delivery status on outgoing messages (single check = sent, double check = read)
- **@mention routing** — direct messages to a specific participant's Claude
- **Respond modes** — cycle own / mentions / all / off with `F3`
- **Shared context** — optionally prepend recent group messages as context to Claude prompts
- **Auto-reconnect** — exponential backoff with status indicator in the status bar

### Encryption
- **E2E relay encryption** — group chat messages are encrypted with AES-256-GCM before leaving your machine. The relay server only sees ciphertext. Key is derived from a passphrase embedded in the connection string via PBKDF2-HMAC-SHA256
- **Local database encryption** — all chat history is encrypted at rest using AES-256-GCM with an auto-generated 256-bit key stored in your data directory (`local.key`)
- **Backward compatible** — existing plaintext messages remain readable after enabling encryption. Encrypted and unencrypted participants can coexist in the same room

## Group Chat

Group chat lets multiple people (each running their own Re:Clawed) share a conversation where every participant's local Claude responds. All messages are end-to-end encrypted by default.

**Create a group**

1. Press `Ctrl+G` and choose **Create**.
2. Re:Clawed starts an embedded WebSocket relay on `localhost:8765` (configurable).
3. If `cloudflared` is installed, a public `wss://...trycloudflare.com` tunnel is opened automatically — no port forwarding needed. Otherwise a LAN `ws://` URL is shown.
4. The connection string includes both the auth token and the encryption passphrase. Copy it and share it with participants.
5. Press **Start Chat** to enter the room.

**Join a group**

1. Press `Ctrl+G` and choose **Join**.
2. Paste the connection string you received (the encryption key is extracted automatically).
3. Press **Join** or hit Enter.

**How it works**

Each participant connects to the same relay room. When you send a message it is encrypted locally, broadcast as ciphertext through the relay, and decrypted by each recipient. Each participant's local `claude` CLI generates its own response, which is also encrypted and broadcast. The relay server is a lightweight WebSocket hub with optional SQLite message log for store-and-forward (missed messages are replayed on reconnect). The server never sees plaintext.

**@mention routing**

You can direct a message at a specific participant's Claude by @mentioning them:

```
@Ed's Claude what do you think about this architecture?
@Ed thoughts?
```

Both the full form (`@Ed's Claude`) and the short form (`@Ed`) are recognised, case-insensitively.

**Group respond modes (F3)**

Press `F3` at any time to cycle through four respond modes. The current mode is shown in the status bar as `[own]`, `[mentions]`, `[all]`, or `[off]`.

| Mode | Your Claude responds to... |
|------|--------------------------|
| `own` (default) | Your own messages only |
| `mentions` | Remote messages that @mention you |
| `all` | Every human message in the room |
| `off` | Nothing — manual browsing only |

The mode is a runtime toggle — it resets to the configured default on restart. You can change the default in `config.toml` with `group_auto_respond = "mentions"`.

**Shared context mode**

By default, each participant's Claude only sees its own conversation history (`isolated` mode). Set `group_context_mode = "shared_history"` in `config.toml` to prepend the last N group messages as context to each Claude prompt. Control the window size with `group_context_window` (default: 20).

**Standalone relay server**

If you want to host a persistent relay separately (e.g. on a VPS):

```bash
reclawed-relay --port 8765 --token mysecret --db /var/lib/reclawed/relay.db
```

```
Options:
  --host TEXT       Interface to bind  [default: 0.0.0.0]
  --port INTEGER    TCP port           [default: 8765]
  --token TEXT      Shared auth token  (env: RELAY_TOKEN)
  --db TEXT         SQLite log path    (env: RELAY_DB; omit to disable)
  --log-level TEXT  Logging level      [default: INFO]
```

## Keybindings

**Always available** (work even while typing):

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line |
| `Ctrl+N` | New chat |
| `Ctrl+S` | Toggle session sidebar |
| `Ctrl+G` | Group chat (Create / Join) |
| `Ctrl+T` | Cycle theme (dark / light / dracula / monokai) |
| `Ctrl+E` | Export session to markdown |
| `Ctrl+P` | View pinned messages |
| `F2` | Cycle model (sonnet / opus / haiku) |
| `F3` | Cycle group respond mode (own / mentions / all / off) |
| `Ctrl+D` / `Ctrl+C` | Quit |

**Navigate mode** (press `Tab` to enter; `Tab` or `Esc` to return to typing):

| Key | Action |
|-----|--------|
| `Up` / `Down` | Select messages |
| `r` | Reply to selected message |
| `e` | Edit selected user message |
| `d` | Delete selected user message |
| `q` | Quote selected into compose |
| `b` | Bookmark / pin toggle |
| `c` | Copy to clipboard |
| `/` | Search messages |
| `Esc` | Deselect / back to compose |
| `?` | Help overlay |

**Sidebar** (when sidebar has focus):

| Key | Action |
|-----|--------|
| `m` | Rename session inline |

## Configuration

Re:Clawed reads a config file on startup. All fields are optional; defaults are shown.

- **macOS**: `~/Library/Application Support/reclawed/config.toml`
- **Linux**: `~/.config/reclawed/config.toml`
- **Windows**: `%APPDATA%\reclawed\config.toml`

```toml
# Path where the SQLite history database is stored.
# macOS default: ~/Library/Application Support/reclawed
# Linux default: ~/.local/share/reclawed
# Windows default: ~/AppData/Local/reclawed
# data_dir = "/custom/path"

# Path (or name on $PATH) of the claude CLI binary.
claude_binary = "claude"

# UI refresh throttle for streaming tokens (milliseconds).
stream_throttle_ms = 50

# Maximum characters of a quoted message sent as reply context to Claude.
max_quote_length = 200

# Starting theme: dark | light | dracula | monokai
theme = "dark"

# Your display name in group chat sessions.
participant_name = "User"

# Local port for the embedded group chat relay server.
relay_port = 8765

# Default group chat respond mode: own | mentions | all | off
# Can be toggled at runtime with F3 (does not persist across restarts).
group_auto_respond = "own"

# Group chat context mode: isolated | shared_history
# "shared_history" prepends recent group messages to each Claude prompt.
group_context_mode = "isolated"

# Number of recent messages included when group_context_mode = "shared_history".
group_context_window = 20
```

## Security

**Local encryption** is automatic — a 256-bit AES key is generated on first launch and stored at `{data_dir}/local.key`. All message content is encrypted before writing to the SQLite database and decrypted transparently on read.

**Group chat encryption** uses AES-256-GCM with a room-level symmetric key. The key is derived from a passphrase (generated per room) via PBKDF2-HMAC-SHA256 with 100,000 iterations and the room ID as salt. The passphrase is embedded in the connection string as a `&key=` parameter so participants only need to share one URL. The relay server never sees plaintext message content.

If the `local.key` file is lost, locally encrypted messages become unreadable. Treat it like a credential and include it in backups.

## Stack

- **textual** — TUI framework
- **cryptography** — AES-256-GCM encryption, PBKDF2 key derivation
- **websockets** — group chat relay (server + client)
- **click** — CLI
- **SQLite** — message and session persistence
- **cloudflared** (optional) — automatic NAT traversal for group chat
