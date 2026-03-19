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
- [x] **Resizable sidebar** — drag to resize sidebar width

## Settings

- [x] **In-app settings screen** — F4 or command palette → discover projects, toggle workspaces, import sessions
- [x] **Change display name** — via command palette
- [x] **Config persistence** — Config.save() writes TOML back to disk
- [ ] **Status message** — like WhatsApp "Hey there! I am using Re:Clawed"
- [x] **Full settings editor** — edit all config fields from the TUI (theme, model, relay, etc.)

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
- [x] **Clickable file references** — file paths in tool activity (Read, Edit, Write, Search) are clickable. Opens DocumentScreen in view mode, or diff mode for Edit tools with before/after capture
- [ ] **Task delegation** — assign specific tasks to specific Claudes in the group
- [ ] **Commit coordination** — Claudes working on different branches can coordinate merges

## Document Viewer & Memory Browser

- [x] **DocumentScreen** — reusable text viewer/editor screen with three modes: view (read-only, syntax highlighted), edit (full TextArea, Ctrl+S to save, unsaved changes warning), and diff (unified diff with green/red line highlighting, hunk navigation with n/p). Supports opening by file path or raw content. Syntax detection from file extension
- [x] **Memory browser** — Ctrl+M opens two-panel screen for browsing Claude's memory files (`~/.claude/projects/{workspace}/memory/`). Left panel lists files with size, right panel shows preview. Create new memories (n), delete with confirmation (d), open in DocumentScreen for full editing (Enter)

## Session Management

- [x] **Auto-naming sessions** — haiku generates 3-5 word names after first exchange (configurable)
- [x] **Generate name on demand** — context menu → "Generate name"
- [x] **Session pinning** — pin sessions to top of workspace via context menu
- [x] **Imported session name cleanup** — strips XML tags and skips system messages
- [x] **Newest first** — sessions sorted by pinned DESC, updated_at DESC
- [x] **Archive / Delete** — context menu (`m` key) already wires both actions to the store; archive soft-hides, delete is permanent
- [ ] **Delete confirmation dialog** — currently delete is instant with no warning; add a modal: "Permanently delete session and N messages? This cannot be undone." with an "Archive instead" link as a safer alternative
- [ ] **Cascade archive for orchestrators** — archiving an orchestrator that has child workers prompts with individual checkboxes: "Archive workers too? i1 ✓, i2 ✓, i3 ✓"
- [ ] **Orchestrator bulk cleanup** — "Archive all completed workers" action in the orchestrator session context menu; cleans up finished instances without touching running ones
- [ ] **Stale instance badge** — worker sessions with status COMPLETE for >24h without being synthesised show a clock badge (🕐) in the sidebar as a visual nudge
- [ ] **Post-synthesis cleanup prompt** — after a synthesis round completes, TUI injects a system notification: "Archive i1, i2?" with one-click confirm. "Keep" dismisses. Orchestrator can also emit `{{CLOSE_WORKERS i1,i2}}` to trigger the same prompt programmatically

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

Hierarchical multi-session workflow — one Claude plans and delegates, child Claude instances execute specific tasks, results flow back up. Designed for power users running structured sprints or ad-hoc parallel work across multiple Claude sessions. The orchestrator focuses on project leadership and quality synthesis; instances do the implementation work.

### What's already built

- [x] **F7 toggle** — promotes a session to orchestrator mode; status bar shows `ORCHESTRATOR` badge
- [x] **Spawn worker from orchestrator** — `{{WORKER task="..." model="..." permissions="..."}}` syntax in orchestrator response triggers worker creation; user sees Spawn / Skip buttons
- [x] **SDK fork (CONTINUATION) dispatch** — worker forks from orchestrator's live SDK session, inherits full conversation history; good for follow-up tasks that need prior context
- [x] **Nested session tree** — worker sessions display indented under their orchestrator in the sidebar; click to switch while others continue in background
- [x] **Worker autonomy** — workers run in their own permission mode (`bypassPermissions` by default); orchestrator keeps its own independent mode
- [x] **Auto-summary on completion** — Haiku generates a 2-3 sentence summary when a worker's stream ends; injected into orchestrator as a system notification
- [x] **Autonomous response loop** — after workers complete (3s debounce), orchestrator auto-responds to assess results and propose follow-up workers; disabled when user is actively typing
- [x] **Worker templates** — preconfigured worker types with system prompts, models, and permission levels defined in `config.toml`
- [x] **Worker bubble fix** — worker UI updates correctly even when user navigates to the worker session after streaming starts (dynamic bubble lookup)
- [x] **Summary truncation fix** — Haiku summary generation uses 3000-char limit for assistant messages (was 300 — caused truncated/confused summaries)

---

### Planned: Template System

Templates are the connective tissue between the orchestrator and its workers. Two kinds: **prompt templates** (what goes into a worker) and **findings templates** (what comes back out). Both are plain markdown files in `templates_dir`, editable from the Orchestrator Settings screen.

#### Prompt templates

- [ ] **`instance_prompt_template`** — a markdown scaffold the orchestrator fills in when creating a FRESH worker's prompt file. Contains: header block (FRESH/CONTINUATION, execution mode, agent selection), skills loading block, hard rules block, memory check block, QA checklist, task definitions section, and footer (priority, output path, required findings structure). The orchestrator reads this template before writing any prompt file — the `dispatch_skill.md` instructs it to do so
- [ ] **Template variable substitution** — TUI fills a fixed set of variables at dispatch time before the orchestrator sees the template: `{date}` (YYYY-MM-DD), `{instance_id}` (i1–i4), `{task_slug}` (kebab-case task name), `{findings_path}` (resolved output path in `findings_dir`), `{workspace_cwd}`. These ensure the filename, output path, and date header are always correct without the orchestrator having to calculate them
- [ ] **Prompt file naming** — generated files follow the pattern `{date}_{instance_id}_{task-slug}.md` in `prompts_dir/`. The slot's `findings_file` is automatically set to the matching path in `findings_dir/` (same filename, different directory) at dispatch time
- [ ] **Multiple named templates** — workspaces can define several prompt templates for different work types (e.g. `implementation.md`, `investigation.md`, `deployment.md`). The orchestrator selects by name in `{{WORKER type="fresh" template="investigation"}}`. Templates listed and editable in the Settings screen

#### Findings templates

- [ ] **`findings_template`** — a required-sections scaffold injected into every FRESH worker's prompt so the worker knows exactly what its output file must contain. Sections typically: Executive Summary, Implementation Details (with line numbers), Testing Results (actual output), Documentation Consistency, Orchestrator Follow-Up (outstanding actions, deployment required, recommendations, risks, blocked items, docs modified), Memory Updates. The worker receives the template content in its prompt; the TUI injects it automatically as part of the FRESH dispatch message
- [ ] **Findings template in preamble** — when dispatching a FRESH worker, TUI builds the worker's first message as: `dispatch_skill.md content` + `{filled prompt template}` + `"Your findings must follow this structure: {findings_template content}"`. The worker has everything it needs in one message

#### Dispatch skill

- [ ] **`dispatch_skill.md`** — a preamble injected at the top of every FRESH worker's first message. Contains standing instructions: read MEMORY.md, check recent findings via Glob, load the specified agents from `.claude/agents/README.md`, apply the pipeline extraction hard rule, follow the QA checklist before writing findings. This is the equivalent of the user's `/prompt` skill — the set of instructions every worker must follow regardless of task. Fully customisable per workspace
- [ ] **Shorthand display** — after a FRESH worker is dispatched, TUI shows a compact summary card in the orchestrator chat (not a system message — displayed in the UI only): instance index, task name, model emoji, prompt file path. Useful reference for the user; matches the "shorthand delivery" format from the original workflow. For external terminal workers, the card is copy-pasteable

---

### Planned: Dual Dispatch Modes

The current SDK fork approach is CONTINUATION-only. The full design adds a second dispatch mode — FRESH — for stateless, predictable workers that start clean from a prompt file.

- [ ] **FRESH dispatch (file-based)** — orchestrator writes a prompt file to `prompts_dir/` using the configured `instance_prompt_template`; TUI fills template variables (`{date}`, `{instance_id}`, `{findings_path}` etc.) and writes the file; spawns a fresh worker session with no SDK fork whose first message is `dispatch_skill content + filled prompt + findings template`. Workers are stateless: no orchestrator conversation history, no hallucination from stale context
- [ ] **FRESH/CONTINUATION per-spawn** — orchestrator specifies dispatch type in the `{{WORKER}}` syntax: `{{WORKER type="fresh" task="..." template="investigation"}}` or `{{WORKER type="continuation" task="..."}}`. Default: continuation if no template named; fresh if a template is specified
- [ ] **External terminal slots** — register a phantom instance slot for a worker running in an external `claude` CLI terminal (outside Re:Clawed). Slot has no `session_id`; completion detected via file watcher only. TUI writes the prompt file and displays the shorthand card for the user to copy-paste into the terminal. Appears in sidebar as `[iN] task… ext` with muted styling
- [ ] **Instance index prefix** — workers display as `[i1] Deploy staging`, `[i2] Pain points audit` in the sidebar; index = lowest free slot (i1→i2→i3→i4, configurable max). Instance indices appear in the `{{WORKER}}` proposal, in the orchestrator preamble, and in generated prompt/findings filenames

---

### Planned: Completion Detection

Three independent signals, configurable per slot, with sensible defaults per dispatch mode.

| Signal | SDK fork | FRESH (Re:Clawed) | External terminal |
|--------|----------|-------------------|-------------------|
| `stream_end` | ✅ natural | ✅ natural | ❌ not visible |
| `findings_file` | ⚠️ optional | ✅ expected | ✅ primary |
| `manual` | ✅ override | ✅ override | ✅ fallback |

- [ ] **File watcher on `findings_dir`** — async polling watches the configured findings directory; fires when a new file stabilises (2s debounce to avoid partial-write false positives). Matches against the slot's expected `findings_file` path (set at spawn time). Unmatched files show an "orphan findings" badge
- [ ] **Per-slot completion signals** — each slot configures which signals count: any combination of `stream_end`, `findings_file`, `manual`. Defaults: SDK = `[stream_end]`; FRESH = `[stream_end, findings_file]`; external = `[findings_file, manual]`
- [ ] **Per-slot relay mode** — `auto` (immediately notify orchestrator when signal fires), `gate` (show ⚑ badge, user clicks "relay"), `manual` (user must trigger). Defaults: SDK = auto; FRESH = gate; external = gate
- [ ] **Orphan findings badge** — file watcher catches findings files with no matching slot; shows "untracked findings" notification; user can associate with a slot or relay directly to orchestrator
- [ ] **File timestamp guard** — file watcher ignores findings files older than the slot's `assigned_at` timestamp, preventing false positives from edits to historical files
- [ ] **Manual signal always available** — user can always type "i1 is done" or use a keybind to manually signal any slot, regardless of its configured relay mode

---

### Planned: Synthesis

User-controlled synthesis of findings from any subset of completed workers. The orchestrator does all the synthesis intelligence; the TUI handles selection and skill injection.

- [ ] **Synthesis checkboxes** — checkboxes appear on COMPLETE workers in the sidebar; hidden on running/idle workers. Any subset can be selected — no forced "all or nothing"
- [ ] **Synthesise button** — "✦ Synthesise (N)" button appears at the bottom of the orchestrator's worker group when ≥1 worker is checked. Shows count of selected
- [ ] **Synthesis message injection** — when triggered, TUI loads `synthesis_skill.md` from the workspace's templates dir, appends the selected workers' findings file paths (resolved from their slot's `findings_file` field), and pre-populates the orchestrator's compose area. User reviews and sends — no magic black box
- [ ] **Sprint vs ad-hoc** — sprint name/scope is optional metadata stored in the runbook; instance slots work identically in both modes. In sprint mode the sidebar shows `Sprint: YYYY-MM-DD Name` above the orchestrator's worker group. TUI does not enforce sprint structure
- [ ] **Post-synthesis cleanup prompt** — after synthesis completes (detected when orchestrator stream ends following a synthesis message), TUI injects a system notification: "Archive workers i1, i2?" with one-click confirm. "Keep" dismisses without archiving. Orchestrator can also emit `{{CLOSE_WORKERS i1,i2}}` to trigger the same prompt

---

### Planned: Runbook

The runbook is the orchestrator's persistent state file — sprint tracking, instance assignment table, lessons learned, system monitoring. Injected as context so the orchestrator always knows its role and current state.

- [ ] **Runbook modal (`Ctrl+R`)** — opens a full-text markdown editor for the configured `runbook_path` file. Section tabs across the top (§2 Monitor, §3 Sprint, §4 History, §5 Lessons…) for quick navigation in large runbooks. `Ctrl+S` saves in-modal, `Esc` closes without saving, "Discard" reverts
- [ ] **Runbook preamble injection** — when orchestrator mode is active, the runbook content (or a configurable excerpt) is prepended to every message sent to the orchestrator. Replaces the existing sparse preamble with a real persistent state. Gives Claude goal awareness, sprint context, and instance assignment table on every turn — even after context compaction
- [ ] **Runbook auto-update** — after synthesis or sprint transitions, orchestrator updates the runbook directly via its file tools; the TUI re-reads it on the next message cycle

---

### Planned: Orchestrator Settings Screen

A dedicated power-user screen for configuring the orchestrator-instance workflow per workspace. Kept separate from the main settings to avoid cluttering the core TUI for users who don't use orchestrator mode.

- [ ] **Dedicated screen** — accessible via command palette ("Orchestrator Settings") or a long-press/secondary action on F7 when already in orchestrator mode. Five sections in a left-nav layout:
  - **Workspace Paths** — `runbook_path`, `prompts_dir`, `findings_dir`, `templates_dir`, `max_instances`; all relative to workspace cwd; stored in the `[[workspaces]]` block in `config.toml`
  - **Templates** — lists all prompt templates in `templates_dir` (`implementation.md`, `investigation.md`, `deployment.md`, etc.) and the findings template; shows line count and last-modified; "Edit" opens in the text editor modal; "New" scaffolds a blank template; "Duplicate" clones an existing one for customisation
  - **Skills** — lists skill definition files (`synthesis-skill.md`, `dispatch-skill.md`) with the same edit/new/duplicate flow; these are injected verbatim so what you write is exactly what the orchestrator or worker receives
  - **Instance Defaults** — default `dispatch_type`, `relay_mode`, `completion_signals`, default model per tier
  - **Completion Rules** — per-workspace overrides; option to require `findings_file` before synthesis is enabled

- [ ] **Template / skill file editor** — reuses the runbook modal editor (same TextArea widget); any file in `templates_dir` can be opened and edited in-app. Changes write directly to disk

- [ ] **Configurable workspace fields in `config.toml`**:
  ```toml
  [[workspaces]]
  name = "voice-of-customer"
  path = "~/GitHub/votc"
  # Orchestrator config (all paths relative to workspace cwd)
  runbook_path = "orchestration_status.md"
  prompts_dir = ".moai/prompts/"
  findings_dir = ".moai/findings/"
  templates_dir = ".moai/templates/"
  max_instances = 4
  # Skills — injected verbatim into orchestrator/worker messages
  synthesis_skill = ".moai/templates/synthesis-skill.md"
  dispatch_skill = ".moai/templates/dispatch-skill.md"
  # Templates — prompt scaffolds (multiple named; orchestrator selects by name)
  findings_template = ".moai/templates/findings-template.md"
  [[workspaces.prompt_templates]]
  name = "implementation"
  path = ".moai/templates/prompt-implementation.md"
  [[workspaces.prompt_templates]]
  name = "investigation"
  path = ".moai/templates/prompt-investigation.md"
  [[workspaces.prompt_templates]]
  name = "deployment"
  path = ".moai/templates/prompt-deployment.md"
  ```

---

### How it differs from existing features

| Feature | Purpose |
|---------|---------|
| **Group chat** | Multiple humans + their Claudes collaborating as peers via relay |
| **Session branching** | Exploring alternative approaches from a conversation checkpoint |
| **Orchestrator/Worker** | Hierarchical delegation — one Claude plans and synthesises, instances execute in isolation, results flow back up |

### Design principles

- **TUI is scaffolding, orchestrator is intelligence** — Re:Clawed handles file watching, slot tracking, skill loading, and synthesis message construction. The orchestrator Claude session handles everything requiring judgment: synthesis phases, conflict resolution, next sprint planning, runbook updates. The 8-phase synthesis protocol lives in `synthesis_skill.md` as a plain file — configurable, versioned, project-specific
- **Workers are stateless by default (FRESH)** — fresh workers don't inherit orchestrator context; they read a prompt file and start clean. This prevents hallucination from stale context and produces predictable, auditable results
- **Power user feature** — the full orchestrator workflow (runbook, file-based dispatch, synthesis, external slots) is opt-in per workspace. Default orchestrator mode (F7) continues to work exactly as today with SDK fork workers. Advanced config only appears in the Orchestrator Settings screen
- **File-based artifacts are first-class** — prompt files and findings files in the repo are auditable records of work. 100+ prompts and findings accumulated over weeks is a feature, not clutter
- **Human controls synthesis timing** — the TUI never auto-synthesises. User selects which completed workers to include and when to trigger. This preserves the "human-in-the-loop" model that makes the pattern reliable

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
