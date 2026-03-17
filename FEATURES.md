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
- [x] **Image attachments** — Alt+V pastes image from clipboard, Alt+A or 📁 button opens file path dialog. Images sent to Claude as base64 multimodal content. Cross-platform: Windows (PowerShell), macOS (pngpaste/osascript), Linux (xclip/wl-paste)
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

## Message Queue & Side Questions

When Claude is busy responding, the user should still be able to compose and queue follow-up messages — and ask quick side questions without derailing the current task.

- [ ] **Message queue** — type and send messages while Claude is still responding. Queued messages are sent in order once the current response completes. Visual indicator showing "2 queued" in the compose area. No more waiting for a response to finish before typing the next thought
- [ ] **/btw side questions** — Claude Code's `/btw` command lets you ask a quick question without interrupting the current work. In the TUI this could be: a keyboard shortcut (e.g. `Ctrl+B`) that opens a lightweight side panel or modal, sends the question to a separate haiku instance, shows the answer, and returns focus to the main conversation. The main Claude session continues uninterrupted. Think of it as a quick lookup while Claude is working — "btw what's the syntax for X?" without losing context
- [ ] **Queue visibility** — show pending messages in the compose area or a small indicator. Allow reordering or cancelling queued messages before they're sent

### Design considerations

- Message queue needs careful handling with the Agent SDK — messages must be sent sequentially after each response completes, not in parallel
- /btw should use a separate lightweight session (haiku, no tools, no session history) to keep it fast and cheap
- In group chat, queued messages should still broadcast in order
- The queue should persist if the user switches sessions — queued messages stay with their session

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

## Git Diff Review Mode

Claude as code reviewer — a dedicated review screen for diffs, PRs, and staged changes, inline in the TUI.

- [ ] **Diff review screen** (`Ctrl+R`) — opens a review view for the active workspace. Shows git diff (staged, unstaged, or branch comparison) with Claude's annotations per hunk. Approve/reject/comment per change
- [ ] **PR review** — pull a PR by number (`Ctrl+R` → enter PR #), Claude reviews the full diff with context-aware comments. Uses `gh` CLI under the hood
- [ ] **Multi-Claude review** — in group chat, both participants' Claudes review the same diff simultaneously and discuss findings in the chat. Different perspectives from different codebases
- [ ] **Review actions** — approve all, request changes, or generate a review summary. Results can be posted as GitHub PR comments via `gh`

## Session Branching / Checkpoints

Git for conversations — save checkpoints, branch from any point, explore different approaches without losing work.

- [ ] **Conversation checkpoints** (`Ctrl+K`) — save a named checkpoint at the current point in the conversation. Stored as a reference to the SDK session ID + message count
- [ ] **Branch from checkpoint** (`Ctrl+B`) — fork the conversation from a checkpoint. Uses SDK's `fork_session=True` with `resume=checkpoint_session_id`. New branch appears in the sidebar under the parent session
- [ ] **Branch tree in sidebar** — visual tree showing conversation branches under each session. Click to switch between branches. Shows message count and cost per branch
- [ ] **Compare branches** — side-by-side view of how two branches diverged. Useful for "I tried approach A and approach B — which worked better?"
- [ ] **Merge branch context** — take findings from an exploratory branch and inject them as context into the main conversation. "I explored Redis in a branch and here's what I learned"

## Orchestrator / Worker Sessions

Hierarchical multi-session workflow — one Claude plans and delegates, child Claude instances execute specific tasks, results flow back up. Automates the common pattern of "architect Claude + implementation Claudes" across a sprint.

- [ ] **Spawn worker from orchestrator** — orchestrator Claude (or user) triggers a new child session for a specific task. Child is forked from orchestrator with the task prompt injected. Appears nested under the parent in the sidebar
- [ ] **Nested session tree** — worker sessions display as collapsible children under their orchestrator in the sidebar. Visual hierarchy: orchestrator → worker 1, worker 2, worker 3. Click to switch between them while others continue in background
- [ ] **Worker autonomy** — workers can run in `bypassPermissions` mode independently. Orchestrator stays in `plan` or `acceptEdits` mode for oversight. Each worker has its own permission level
- [ ] **Auto-summary on completion** — when a worker finishes (detects completion or user marks done), a summary (commit hashes, changes made, edge cases found) is auto-injected into the orchestrator's context. Keeps orchestrator clean and focused
- [ ] **Sprint tracking** — orchestrator maintains a live sprint doc. As workers complete tasks, the doc updates with status, commit refs, and any issues found. Visible as a pinned message or dedicated panel
- [ ] **Orchestrator-initiated delegation** — orchestrator Claude can suggest spawning workers: "This has 3 independent tasks — want me to spin up workers for each?" User approves, workers launch in parallel
- [ ] **Worker templates** — preconfigured worker types: "implementation sprint", "test writer", "code reviewer", "documentation". Each gets a tailored system prompt and permission level

### How it differs from existing features

| Feature | Purpose |
|---------|---------|
| **Group chat** | Multiple humans + their Claudes collaborating as peers |
| **Session branching** | Exploring alternative approaches from a checkpoint |
| **Orchestrator/Worker** | Hierarchical delegation — one Claude plans, children execute, results flow up |

### Design considerations

- Workers are full `ClaudeSession` instances, not SDK subagents — they get their own context window, tools, and permissions
- Fork from orchestrator carries the high-level plan but not implementation details (keeps worker context clean)
- The orchestrator never sees raw code diffs from workers — only summaries. This preserves orchestrator context for strategic decisions
- Workers could be different models: orchestrator on Opus for planning, workers on Sonnet for speed
- In group chat, Tommy's orchestrator could delegate to Tommy's workers while Ed's orchestrator delegates to Ed's workers — coordinated via the relay

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
