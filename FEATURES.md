# Re:Clawed Feature Backlog

Living document for feature ideas, grouped by theme. Completed items marked with checkmarks.

## Workspaces / Multi-Project

- [x] **Workspace sections in sidebar** — each cwd/project gets its own collapsible section
- [x] **Import existing sessions** — auto-discover from `~/.claude/projects/`, import via Settings screen
- [x] **New chat in any workspace** — `+ New Chat` per workspace section, Ctrl+N uses current workspace
- [x] **Default workspace** — sessions without a workspace go under "Default" section
- [x] **Workspace badge** — current workspace shown in status bar
- [ ] **Per-workspace config** — different models, permissions, tools per workspace

## Settings

- [x] **In-app settings screen** — F4 or command palette → discover projects, toggle workspaces, import sessions
- [x] **Change display name** — via command palette
- [x] **Config persistence** — Config.save() writes TOML back to disk
- [ ] **Status message** — like WhatsApp "Hey there! I am using Re:Clawed"
- [ ] **Full settings editor** — edit all config fields from the TUI (theme, model, relay, etc.)

## Group Chat Infrastructure

- [x] **Persistent relay daemon** — relay server runs as background subprocess, survives TUI quit/restart
- [x] **Remote relay mode** — team-hosted relay on a VPS with stable URL
- [x] **Background relay connections** — pooled like Claude sessions; receive messages while viewing another chat
- [x] **sync_response handling** — missed messages replayed on reconnect
- [x] **Unread badges for group chats** — background messages increment unread count
- [ ] **Named Cloudflare tunnels** — stable tunnel URLs that survive daemon restarts (requires Cloudflare account)

## Profiles

- [ ] **Profiles** (Work, Personal, Custom) — separate contexts with their own settings, theme, participant name
- [ ] **Profile switching** — quick toggle between profiles without restarting

## Interactivity

- [x] **Tool activity display** — real-time tool activity shown inline in message bubbles (Reading, Editing, Running, Searching...) with collapsible details
- [x] **Tool approval UI** — when Claude needs permission, approve/deny buttons appear inline. SDK `can_use_tool` callback bridges to TUI via asyncio.Future
- [x] **Question handling** — detects when Claude asks a question, highlights the bubble with accent border
- [x] **Choice selection** — numbered options rendered as clickable buttons, auto-fills compose area on click

## Visuals

- [x] **Status bar redesign** — decluttered minimal bar. Only shows what matters NOW. Conditional badges (bypass perms, room mode) appear only when non-default
- [x] **Context gauge** — `████████░░ 78%` progress bar showing context window usage. Tracks input_tokens from SDK, persisted per-session
- [x] **Full settings editor** — tabbed settings screen (General, Claude, Group Chat, Workspaces) with Select dropdowns and Input fields. All config fields editable from TUI
- [ ] **Color-coded workspace badges** — different colors per workspace in status bar
- Open to ideas

## Group Chat Enhancements

- [x] **Invite to chat** — Ctrl+I upgrades a 1:1 session into a group. Claude keeps full context, messages stay. Connection string generated for sharing
- [x] **Clear room modes** — F3 cycles per-room synchronized modes: Humans Only, Claude Assists, Full Auto, C2C. Broadcast via relay so all participants see the same mode
- [x] **Mid-chat permission switching** — F5 cycles permission modes (default/acceptEdits/bypassPermissions) without losing context. Per-session, persisted. Status bar shows current mode
- [x] **Autonomous Claude-to-Claude** — C2C mode + bypassPermissions = Claudes work together overnight with full filesystem access
- [ ] **Task delegation** — assign specific tasks to specific Claudes in the group
- [ ] **Commit coordination** — Claudes working on different branches can coordinate merges
