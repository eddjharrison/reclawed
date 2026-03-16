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

- [ ] **Tool approval UI** — when Claude asks for permission, show an interactive prompt in the TUI
- [ ] **Question handling** — detect clarifying questions and make it easy to respond
- [ ] **Choice selection** — when Claude presents numbered options, allow clicking or pressing 1/2/3

## Visuals

- [ ] **Usage toolbar** — show context window usage, token budget remaining, cost so far
- [ ] **Context indicator** — visual indicator of how much context Claude has
- [ ] **Color-coded workspace badges** — different colors per workspace in status bar
- Open to ideas

## Group Chat Enhancements

- [ ] **Autonomous Claude-to-Claude** — Claudes can continue working together while humans are away
- [ ] **Task delegation** — assign specific tasks to specific Claudes in the group
- [ ] **Commit coordination** — Claudes working on different branches can coordinate merges
