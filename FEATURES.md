# Re:Clawed Feature Backlog

Living document for feature ideas, grouped by theme. Completed items marked with checkmarks.

## Workspaces / Multi-Project

- [x] **Workspace sections in sidebar** — each cwd/project gets its own collapsible section
- [x] **Import existing sessions** — auto-discover from `~/.claude/projects/`, import via Settings screen
- [x] **New chat in any workspace** — `+` per workspace header, F6 workspace picker, Ctrl+N in current workspace
- [x] **Default workspace** — sessions without a workspace go under "Default" section
- [x] **Workspace badge** — current workspace shown in status bar with color
- [x] **Per-workspace config** — different models, permissions, tools per workspace in config.toml
- [x] **Color-coded workspace badges** — auto-assigned from palette (cyan, yellow, green, magenta, blue, red)
- [x] **Workspace removal** — right-click header to remove with confirmation
- [x] **Session refresh** — `r` button in workspace header to re-import from Claude Code
- [ ] **Resizable sidebar** — drag to resize sidebar width

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
- [x] **Choice selection** — numbered options rendered as clickable buttons, auto-submit on click
- [x] **AskUserQuestion widget** — multi-question forms with clickable options, collect-then-submit, matches Claude Code CLI
- [ ] **Task delegation** — assign specific tasks to specific Claudes in the group
- [ ] **Commit coordination** — Claudes working on different branches can coordinate merges

## Session Management

- [x] **Auto-naming sessions** — haiku generates 3-5 word names after first exchange (configurable)
- [x] **Generate name on demand** — context menu → "Generate name"
- [x] **Session pinning** — pin sessions to top of workspace via context menu
- [x] **Imported session name cleanup** — strips XML tags and skips system messages
- [x] **Newest first** — sessions sorted by pinned DESC, updated_at DESC

## Visuals

- [x] **Status bar redesign** — battery gauge, model emoji (🧠/🤖/⚡), git branch+status, permission badges, workspace color
- [x] **Context gauge** — draining battery style, green/yellow/red based on remaining context
- [x] **Status bar visible** — fixed dock:bottom compression bug
- [x] **Full settings editor** — tabbed settings screen (General, Claude, Group Chat, Workspaces)
- [x] **Quit confirmation** — Ctrl+D shows confirm dialog with y/n/arrow key navigation
- Open to ideas

## Windows Polish

- [x] **No extra terminal window** — subprocess CREATE_NO_WINDOW patch for all processes including SDK
- [x] **Clean exit** — suppressed asyncio ResourceWarning tracebacks
- [x] **Ctrl+Enter newlines** — Windows Terminal sends ctrl+j for Ctrl+Enter
- [x] **No ANSI leakage** — naming subprocess uses NO_COLOR=1 + stdin/stderr DEVNULL

## Group Chat Enhancements

- [x] **Invite to chat** — Ctrl+I upgrades a 1:1 session into a group. Claude keeps full context, messages stay. Connection string generated for sharing
- [x] **Clear room modes** — F3 cycles per-room synchronized modes: Humans Only, Claude Assists, Full Auto, C2C. Broadcast via relay so all participants see the same mode
- [x] **Mid-chat permission switching** — F5 cycles permission modes (default/plan/acceptEdits/bypassPermissions) without losing context. Per-session, persisted
- [x] **Autonomous Claude-to-Claude** — C2C mode + bypassPermissions = Claudes work together overnight with full filesystem access
- [ ] **Task delegation** — assign specific tasks to specific Claudes in the group
- [ ] **Commit coordination** — Claudes working on different branches can coordinate merges

## Extensibility / Plugin Ecosystem

The TUI should integrate with Claude Code's extensibility features — plugins, skills, MCP servers — and provide a way to discover, install, and manage them without leaving the app.

### Core ideas

- [ ] **MCP server management** — browse installed MCP servers, enable/disable per workspace, see connection status in status bar. Config lives in `.claude/settings.json` but the TUI should surface it
- [ ] **Skills browser** — list available skills (local `.claude/skills/` + global `~/.claude/skills/`), preview what they do, enable/disable per session or workspace
- [ ] **Plugin marketplace** — browse and install community plugins/skills/MCP servers from a registry. Think VS Code extensions panel but for Claude Code capabilities
- [ ] **Scope levels** — clear distinction between global (user-wide), project (workspace), and session-level configuration. UI should make it obvious what applies where
- [ ] **Preconfigured bundles** — curated sets of skills + MCP servers for common project types (e.g. "Python backend" bundle includes python-expert skill, database MCP, test runner). Could ship as templates or be community-contributed
- [ ] **Auto-detection** — Claude analyzes the project (package.json, pyproject.toml, Dockerfile, etc.) and suggests which skills, MCP servers, and tools would be useful. "This looks like a Next.js project — want to enable the frontend-developer skill and Supabase MCP?"
- [ ] **Hooks management** — view and edit Claude Code hooks (SessionStart, PreCompact, UserPromptSubmit) from the TUI. Currently requires manual `.claude/settings.json` editing

### Design considerations

- The TUI wraps Claude Code — it shouldn't duplicate Claude Code's own config system, but rather provide a friendlier interface to it
- Plugin/skill installation should modify `.claude/` files that Claude Code itself reads, so everything stays compatible if the user switches between the TUI and raw CLI
- Per-workspace overrides (already implemented for model/permissions/tools) should extend naturally to skills and MCP servers
- The marketplace concept depends on whether a community registry exists — start with local browsing first, add remote discovery later
