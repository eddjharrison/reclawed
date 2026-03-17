---
name: websocket-relay
description: >
  WebSocket relay architecture for Re:Clawed group chat. Covers relay daemon,
  client connections, message broadcasting, room modes, and reconnection.
license: MIT
compatibility: Designed for Claude Code
allowed-tools: Read Grep Glob Bash
user-invocable: false
metadata:
  version: "1.0.0"
  category: "domain"
  status: "active"
  updated: "2026-03-17"
  tags: "websocket, relay, group-chat, daemon, broadcast"

triggers:
  keywords: ["relay", "WebSocket", "group chat", "daemon", "broadcast", "room", "invite", "C2C"]
  languages: ["python"]
---

# WebSocket Relay — Re:Clawed Group Chat

Architecture and patterns for the relay-based group chat system.

## Quick Reference

### Architecture

```
TUI Client A ←→ Relay Server ←→ TUI Client B
                    ↕
               Claude Sessions
```

- **Relay Daemon** — background process (survives TUI quit/restart)
- **Modes**: `local` (localhost:8765) or `remote` (team VPS)
- **Room Modes** (F3 cycle): Humans Only → Claude Assists → Full Auto → C2C
- **Connection**: pooled in background, messages arrive even when viewing other chats

### Room Modes

| Mode | Description |
|------|-------------|
| Humans Only | Claude doesn't auto-respond |
| Claude Assists | Claude responds when mentioned or asked |
| Full Auto | Claude responds to every message |
| C2C | Claude-to-Claude autonomous work |

### Message Flow

1. User types message in TUI
2. ComposeArea.Submitted → ChatScreen._send_message()
3. If group chat: broadcast via relay WebSocket
4. Relay fans out to all connected clients
5. Each client renders in their message list
6. If mode allows, Claude session receives and responds

### Key Config

```toml
relay_port = 8765
relay_mode = "local"        # or "remote"
group_auto_respond = "claude_assists"
group_context_mode = "isolated"
group_context_window = 20
```

### Key Files

| File | Purpose |
|------|---------|
| `src/reclawed/relay/daemon.py` | Daemon lifecycle (start/stop/status) |
| `src/reclawed/relay/server.py` | WebSocket server, room management |
| `src/reclawed/relay/client.py` | Client connections, reconnection |
| `src/reclawed/relay/protocol.py` | Message types and serialization |

### Invite Flow (Ctrl+I)

1. User presses Ctrl+I in a 1:1 session
2. Session upgraded to group — Claude keeps full context
3. Connection string generated for sharing
4. Other participants connect via relay
5. Messages broadcast to all, unread badges update in background
