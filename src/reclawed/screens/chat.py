"""Main chat screen — orchestrates message sending, receiving, and interaction."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header

from reclawed.claude import (
    StreamError, StreamResult, StreamSessionId, StreamToken,
    StreamToolResult, StreamToolUse,
)
from reclawed.claude_session import ClaudeSession
from reclawed.config import Config, THEME_CYCLE, THEME_MAP
from reclawed.crypto import decrypt_content, derive_room_key, is_encrypted
from reclawed.relay.protocol import RelayMessage
from reclawed.models import Message, Session
from reclawed.relay.client import RelayClient
from reclawed.store import Store
from reclawed.utils import copy_to_clipboard
from reclawed.widgets.chat_sidebar import ChatSidebar
from reclawed.widgets.compose_area import ComposeArea
from reclawed.widgets.message_bubble import MessageBubble
from reclawed.widgets.message_list import MessageList
from reclawed.widgets.quote_preview import QuotePreview
from reclawed.widgets.status_bar import StatusBar


class ChatScreen(Screen):
    """Main chat screen."""

    BINDINGS = [
        # priority=True ensures these work even when TextArea has focus
        Binding("ctrl+d", "quit", "Quit", show=True, key_display="^D", priority=True),
        Binding("ctrl+n", "new_chat", "New Chat", show=True, priority=True),
        Binding("f6", "workspace_new_chat", "New Chat in...", show=False, priority=True),
        Binding("ctrl+g", "group_menu", "Group", show=True, key_display="^G", priority=True),
        Binding("ctrl+i", "invite_to_chat", "Invite", show=True, key_display="^I", priority=True),
        Binding("ctrl+s", "toggle_sidebar", "Sidebar", show=True, priority=True),
        Binding("ctrl+t", "cycle_theme", "Theme", show=True, key_display="^T", priority=True),
        Binding("ctrl+e", "export_markdown", "Export", show=True, key_display="^E", priority=True),
        Binding("ctrl+p", "pinned", "Pinned", show=True, key_display="^P", priority=True),
        Binding("f2", "cycle_model", "Model", show=True, key_display="F2", priority=True),
        Binding("f3", "cycle_respond_mode", "Respond mode", show=True, key_display="F3", priority=True),
        Binding("f4", "settings", "Settings", show=True, key_display="F4", priority=True),
        Binding("f5", "cycle_permission", "Permissions", show=True, key_display="F5", priority=True),
        # These only work in navigate mode (compose not focused)
        Binding("tab", "toggle_focus", "Navigate/Type", show=True, key_display="Tab"),
        Binding("up", "select_prev", "Prev msg", show=False),
        Binding("down", "select_next", "Next msg", show=False),
        Binding("r", "reply", "Reply", show=True, key_display="r"),
        Binding("q", "quote", "Quote", show=True, key_display="q"),
        Binding("b", "bookmark", "Bookmark", show=True, key_display="b"),
        Binding("c", "copy_message", "Copy", show=True, key_display="c"),
        Binding("e", "edit_message", "Edit", show=True, key_display="e"),
        Binding("d", "delete_message", "Delete", show=True, key_display="d"),
        Binding("slash", "search", "Search", show=True, key_display="/"),
        Binding("escape", "deselect", "Back to compose", show=False),
        Binding("question_mark", "help", "Help", show=True, key_display="?"),
    ]

    # Ordered list of models to cycle through with Ctrl+M.
    # Each entry is a short alias passed verbatim to ``--model`` on the CLI.
    MODELS = ["sonnet", "opus", "haiku"]

    # Known context window sizes per model family
    _CONTEXT_WINDOWS = {"opus": 200_000, "sonnet": 200_000, "haiku": 200_000}

    # Room modes — clear, per-room, synchronized via relay
    ROOM_MODES = ["humans_only", "claude_assists", "full_auto", "claude_to_claude"]
    ROOM_MODE_LABELS = {
        "humans_only": "Humans Only",
        "claude_assists": "Claude Assists",
        "full_auto": "Full Auto",
        "claude_to_claude": "C2C",
    }
    ROOM_MODE_DESCRIPTIONS = {
        "humans_only": "No Claude responds unless @mentioned",
        "claude_assists": "Claude responds to your messages only",
        "full_auto": "All Claudes respond to all human messages",
        "claude_to_claude": "Claudes work autonomously",
    }
    # Map old mode names to new for backward compatibility
    _MODE_COMPAT = {"own": "claude_assists", "mentions": "humans_only", "all": "full_auto", "off": "humans_only"}

    # Permission modes — can be switched mid-chat via F5
    PERMISSION_MODES = ["default", "plan", "acceptEdits", "bypassPermissions"]
    PERMISSION_MODE_LABELS = {
        "default": "Default",
        "plan": "Plan Mode",
        "acceptEdits": "Accept Edits",
        "bypassPermissions": "BYPASS PERMISSIONS",
    }
    PERMISSION_MODE_DESCRIPTIONS = {
        "default": "Claude asks for approval on every action",
        "plan": "Claude creates a plan for approval before acting",
        "acceptEdits": "Claude can read and edit files without asking",
        "bypassPermissions": "Claude has unrestricted access — no approval needed",
    }

    def __init__(self, store: Store, config: Config, session: Session | None = None) -> None:
        super().__init__()
        self.store = store
        self.config = config
        if session:
            self.session = session
        else:
            # Try to resume the most recent session instead of creating empty ones
            sessions = store.list_sessions()
            self.session = sessions[0] if sessions else self._create_new_session()
        self._claude: ClaudeSession | None = None
        self._claude_sessions: dict[str, ClaudeSession] = {}  # pool of live sessions
        self._sending = False
        # Restore the model stored on the session, or start with no override
        # (None means the CLI will use its own default).
        self._selected_model: str | None = self.session.model
        # Permission mode — per-session, can be switched mid-chat via F5
        self._selected_permission: str = (
            self.session.permission_mode or config.permission_mode
        )
        # Group chat relay state
        self._relay_client: RelayClient | None = None  # active session's relay
        self._tunnel_proc = None   # cloudflared subprocess
        self._relay_receive_task: asyncio.Task | None = None  # active session's task
        # Pool of live relay connections (like _claude_sessions for Claude)
        self._relay_clients: dict[str, RelayClient] = {}
        self._relay_receive_tasks: dict[str, asyncio.Task] = {}
        # Room mode — per-room, synchronized via relay, persisted on Session
        _default = self._MODE_COMPAT.get(config.group_auto_respond, config.group_auto_respond)
        if _default not in self.ROOM_MODES:
            _default = "claude_assists"
        self._group_respond_mode: str = _default
        # Typing indicator tracking: {sender_name: monotonic_time}
        self._typing_users: dict[str, float] = {}
        self._typing_timer_running = False
        # Read receipts tracking: {participant_id: highest_seq_read}
        self._read_receipts: dict[str, int] = {}
        # Map local message IDs to relay seqs for read receipt/edit/delete
        self._msg_id_to_seq: dict[str, int] = {}
        # Queue of outgoing local message IDs waiting for echo seq mapping
        self._pending_echo_ids: list[str] = []
        # Pending tool approval futures: {tool_use_id: asyncio.Future}
        self._pending_approvals: dict[str, asyncio.Future] = {}

    def _effective_allowed_tools(self, cwd: str | None = None) -> list[str]:
        """Return allowed tools for the given cwd, checking workspace overrides."""
        ws = self.config.workspace_for_cwd(cwd)
        tools_str = (ws.allowed_tools if ws and ws.allowed_tools is not None
                     else self.config.allowed_tools)
        return tools_str.split(",")

    def _create_new_session(self, cwd: str | None = None) -> Session:
        session = Session(cwd=cwd)
        self.store.create_session(session)
        return session

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-layout"):
            yield ChatSidebar(self.store, workspaces=self.config.workspaces, id="chat-sidebar")
            with Vertical(id="chat-panel"):
                yield MessageList(id="message-list")
                yield QuotePreview(id="quote-preview")
                yield StatusBar(id="status-bar")
                yield ComposeArea(id="compose-area")
        yield Footer()

    async def _start_claude_session(
        self,
        resume_id: str | None = None,
        fork: bool = False,
    ) -> None:
        """Create or reuse a ClaudeSession for the current chat.

        Sessions are pooled in ``_claude_sessions`` so switching between
        chats doesn't destroy background work.  If a session already has
        a live client, we just point ``_claude`` at it.
        """
        session_key = self.session.id

        # Reuse existing client if we already have one for this session
        if session_key in self._claude_sessions:
            self._claude = self._claude_sessions[session_key]
            return

        # Reset send state for the new session's UI
        self._sending = False
        try:
            compose = self.query_one("#compose-area", ComposeArea)
            compose.set_enabled(True)
        except Exception:
            pass

        session = ClaudeSession(
            cli_path=self.config.claude_binary,
            session_id=resume_id,
            fork_session=fork,
            model=self._selected_model,
            cwd=self.session.cwd,
            permission_mode=self._selected_permission,
            allowed_tools=self._effective_allowed_tools(self.session.cwd),
            approval_callback=self._on_tool_approval_needed,
        )
        self._claude_sessions[session_key] = session
        self._claude = session

        status = self.query_one("#status-bar", StatusBar)
        status.set_connection_status("Initializing Claude...")

        async def _init():
            await session.start()
            try:
                status.set_connection_status(None)
            except Exception:
                pass

        asyncio.create_task(_init())

    async def on_mount(self) -> None:
        self._update_status()
        # Highlight the active session in the sidebar
        sidebar = self.query_one("#chat-sidebar", ChatSidebar)
        sidebar.refresh_sessions(active_session_id=self.session.id)
        # Load existing messages if resuming a session
        if self.session.message_count > 0:
            await self._load_session_messages()
        # Start the Claude SDK session (resume if we have a prior session ID)
        await self._start_claude_session(resume_id=self.session.claude_session_id)
        # Ensure relay daemon is running before reconnecting group sessions
        has_groups = self.session.is_group or any(
            s.is_group and s.relay_url for s in self.store.list_sessions()
        )
        if has_groups and self.config.relay_mode == "local":
            try:
                from reclawed.relay.daemon import ensure_daemon
                await asyncio.to_thread(
                    ensure_daemon, self.config.data_dir, self.config.relay_port,
                )
            except Exception:
                pass  # Non-fatal — relay connections will retry with backoff

        # Auto-reconnect ALL group sessions on startup (non-blocking)
        if self.session.is_group and self.session.relay_url:
            asyncio.create_task(self._try_reconnect_group())
        # Also reconnect background group sessions so they receive messages
        for s in self.store.list_sessions():
            if s.is_group and s.relay_url and s.id != self.session.id:
                asyncio.create_task(self._background_reconnect_group(s))

    async def _load_session_messages(self) -> None:
        msg_list = self.query_one("#message-list", MessageList)
        messages = self.store.get_session_messages(self.session.id)
        for msg in messages:
            await msg_list.add_message(msg)

    def _update_status(self) -> None:
        status = self.query_one("#status-bar", StatusBar)
        group_mode = self._group_respond_mode if self.session.is_group else None
        ws = self.config.workspace_for_cwd(self.session.cwd)
        workspace_name = ws.name if ws else None
        workspace_color = ws.color if ws else "yellow"
        status.update_info(
            session_name=self.session.name,
            model=self.session.model,
            cost=self.session.total_cost_usd,
            message_count=self.session.message_count,
            group_mode=group_mode,
            clear_group_mode=not self.session.is_group,
            workspace_name=workspace_name,
            workspace_color=workspace_color,
            permission_mode=self._selected_permission,
            cwd=self.session.cwd,
        )
        status.set_encrypted(bool(self.session.encryption_passphrase))
        # Restore context gauge from persisted value
        if self.session.last_input_tokens:
            ctx_max = self._get_context_window_size()
            status.set_context(self.session.last_input_tokens, ctx_max)

    # --- Message handling ---

    async def on_compose_area_submitted(self, event: ComposeArea.Submitted) -> None:
        # Handle edit mode
        if event.editing_message_id:
            await self._handle_edit_submit(event.editing_message_id, event.text)
            return

        if self._sending:
            return
        self._sending = True
        compose = self.query_one("#compose-area", ComposeArea)
        compose.set_enabled(False)

        quote_preview = self.query_one("#quote-preview", QuotePreview)
        reply_to_id = quote_preview.reply_to_id
        reply_context = None

        if reply_to_id:
            parent_msg = self.store.get_message(reply_to_id)
            if parent_msg:
                reply_context = parent_msg.content[:self.config.max_quote_length]
            quote_preview.hide()

        # Create and display user message
        user_msg = Message(
            role="user",
            content=event.text,
            session_id=self.session.id,
            reply_to_id=reply_to_id,
            sender_name=self.config.participant_name if self.session.is_group else None,
            sender_type="human" if self.session.is_group else None,
        )
        self.store.add_message(user_msg)

        msg_list = self.query_one("#message-list", MessageList)
        await msg_list.add_message(user_msg)

        # In group sessions, broadcast the user's message to all participants.
        if self.session.is_group and self._relay_client is not None:
            try:
                self._pending_echo_ids.append(user_msg.id)
                await self._relay_client.send_message(event.text, sender_type="human")
            except Exception:
                pass  # Best-effort; don't break the local send flow

        # In "Humans Only" mode, skip Claude unless the user @mentions their Claude.
        if self.session.is_group and self._group_respond_mode == "humans_only":
            if not self._is_mentioned(event.text):
                self._sending = False
                compose = self.query_one("#compose-area", ComposeArea)
                compose.set_enabled(True)
                compose.query_one("#compose-input").focus()
                return

        # Build prompt with optional group context preamble
        prompt = event.text
        if self.session.is_group:
            preamble = self._build_group_context_preamble()
            if preamble:
                prompt = preamble + "\n\n" + prompt

        # Create placeholder assistant message
        claude_name = f"{self.config.participant_name}'s Claude" if self.session.is_group else None
        assistant_msg = Message(
            role="assistant",
            content="...",
            session_id=self.session.id,
            sender_name=claude_name,
            sender_type="claude" if self.session.is_group else None,
        )
        self.store.add_message(assistant_msg)
        await msg_list.add_message(assistant_msg)

        # Stream response
        self._stream_response(prompt, assistant_msg, reply_context)

    # --- Group chat relay helpers ---

    async def _try_reconnect_group(self) -> None:
        """Attempt to reconnect a group session on startup, silently fail if unreachable."""
        try:
            await self._start_relay_client(self.session)
        except Exception:
            self.notify("Group relay unavailable — use Ctrl+G to rejoin", timeout=5)

    async def _background_reconnect_group(self, session: Session) -> None:
        """Silently reconnect a background group session into the pool."""
        # Save active pointers so _start_relay_client doesn't overwrite them
        prev_client = self._relay_client
        prev_task = self._relay_receive_task
        try:
            await self._start_relay_client(session, silent=True)
        except Exception:
            pass  # Silent — this is a background reconnection
        # Restore active pointers (background session shouldn't become active)
        self._relay_client = prev_client
        self._relay_receive_task = prev_task

    async def _start_relay_client(self, session: Session, silent: bool = False) -> None:
        """Create or reuse a pooled RelayClient for the given group session.

        Relay clients are pooled in ``_relay_clients`` so switching between
        sessions doesn't kill background connections — mirroring the Claude
        session pooling in ``_claude_sessions``.

        Set ``silent=True`` for background reconnections that shouldn't
        spam the user with notifications.
        """
        if session.relay_url is None or session.room_id is None:
            return

        # Reuse existing client if already pooled for this session
        if session.id in self._relay_clients:
            self._relay_client = self._relay_clients[session.id]
            self._relay_receive_task = self._relay_receive_tasks.get(session.id)
            return

        participant_id = session.participant_id or str(uuid.uuid4())
        room_key: bytes | None = None
        if session.encryption_passphrase and session.room_id:
            room_key = derive_room_key(session.encryption_passphrase, session.room_id)
        client = RelayClient(
            url=session.relay_url,
            room_id=session.room_id,
            participant_id=participant_id,
            participant_name=self.config.participant_name,
            participant_type="human",
            token=session.relay_token,
            room_key=room_key,
        )
        client.set_status_callback(self._make_relay_status_callback(session.id))
        try:
            if not silent:
                self.notify("Connecting to relay...", timeout=3)
            await client.connect(timeout=10.0)
            # Pool the client and start a session-bound receive loop
            self._relay_clients[session.id] = client
            self._relay_client = client
            task = asyncio.create_task(
                self._relay_receive_loop(session.id),
                name=f"relay-receive-{session.id[:8]}",
            )
            self._relay_receive_tasks[session.id] = task
            self._relay_receive_task = task
            if not silent:
                self.notify(f"Connected to group: {session.room_id[:8]}...", timeout=3)
        except TimeoutError:
            if not silent:
                self.notify("Relay connection timed out — check the URL and try again", severity="error", timeout=8)
        except Exception as exc:
            if not silent:
                self.notify(f"Relay connect failed: {exc}", severity="error", timeout=8)

    async def _relay_receive_loop(self, session_id: str) -> None:
        """Background task: receive relay messages for a specific session.

        Runs for the lifetime of the pooled relay connection, regardless of
        which session is active in the UI.  Store writes always happen;
        UI updates are gated on ``_is_active()``.
        """
        client = self._relay_clients.get(session_id)
        if client is None:
            return

        def _is_active() -> bool:
            return self.session.id == session_id

        try:
            async for relay_msg in client.receive_messages():
                # Echo from own messages — capture seq for read receipt mapping
                if relay_msg.sender_id == client._participant_id:
                    if relay_msg.type == "message" and relay_msg.seq and self._pending_echo_ids:
                        local_id = self._pending_echo_ids.pop(0)
                        self._msg_id_to_seq[local_id] = relay_msg.seq
                    continue

                # Handle sync_response — replay missed messages
                if relay_msg.type == "sync_response":
                    await self._handle_sync_response(relay_msg, session_id, client, _is_active)
                    continue

                # Handle room mode changes (synchronized across all participants)
                if relay_msg.type == "room_mode" and relay_msg.content:
                    new_mode = relay_msg.content
                    if new_mode in self.ROOM_MODES:
                        self._group_respond_mode = new_mode
                        session_obj = self.store.get_session(session_id)
                        if session_obj:
                            session_obj.room_mode = new_mode
                            self.store.update_session(session_obj)
                        if _is_active():
                            self.session.room_mode = new_mode
                            self._update_status()
                            label = self.ROOM_MODE_LABELS.get(new_mode, new_mode)
                            self.notify(
                                f"{relay_msg.sender_name} changed mode to: {label}",
                                timeout=3,
                            )
                    continue

                # Extract room mode from presence updates (for new joiners)
                if relay_msg.type in ("join", "presence") and relay_msg.content:
                    if relay_msg.content in self.ROOM_MODES:
                        self._group_respond_mode = relay_msg.content
                        if _is_active():
                            self.session.room_mode = relay_msg.content
                            self._update_status()

                # Handle typing indicators (UI-only, skip if not active)
                if relay_msg.type == "typing":
                    if _is_active():
                        self._typing_users[relay_msg.sender_name] = time.monotonic()
                        status = self.query_one("#status-bar", StatusBar)
                        status.set_typing_indicator(list(self._typing_users.keys()))
                        self._start_typing_timer()
                    continue

                # Handle read receipts (UI-only, skip if not active)
                if relay_msg.type == "read" and relay_msg.read_up_to_seq is not None:
                    if _is_active():
                        self._read_receipts[relay_msg.sender_id] = relay_msg.read_up_to_seq
                        self._update_delivery_status()
                    continue

                # Handle edits from remote participants (store always, UI if active)
                if relay_msg.type == "edit" and relay_msg.target_message_id:
                    target_msg = self.store.get_message(relay_msg.target_message_id)
                    if target_msg:
                        from datetime import datetime, timezone as tz
                        target_msg.content = relay_msg.content or ""
                        target_msg.edited_at = datetime.now(tz.utc)
                        self.store.update_message(target_msg)
                        if _is_active():
                            msg_list = self.query_one("#message-list", MessageList)
                            bubble = msg_list.get_bubble(relay_msg.target_message_id)
                            if bubble:
                                bubble.update_content(target_msg.content)
                                bubble._message.edited_at = target_msg.edited_at
                    continue

                # Handle deletes from remote participants (store always, UI if active)
                if relay_msg.type == "delete" and relay_msg.target_message_id:
                    target_msg = self.store.get_message(relay_msg.target_message_id)
                    if target_msg:
                        self.store.soft_delete_message(relay_msg.target_message_id)
                        if _is_active():
                            msg_list = self.query_one("#message-list", MessageList)
                            bubble = msg_list.get_bubble(relay_msg.target_message_id)
                            if bubble:
                                await bubble.mark_deleted()
                    continue

                # Ignore non-message types (presence/heartbeat/system)
                if relay_msg.type != "message":
                    continue

                # Store message — always, regardless of active state
                msg = Message(
                    role="user" if relay_msg.sender_type == "human" else "assistant",
                    content=relay_msg.content or "",
                    session_id=session_id,
                    sender_name=relay_msg.sender_name,
                    sender_type=relay_msg.sender_type,
                )
                self.store.add_message(msg)

                if relay_msg.seq:
                    self._msg_id_to_seq[msg.id] = relay_msg.seq

                if _is_active():
                    # Render to screen
                    msg_list = self.query_one("#message-list", MessageList)
                    await msg_list.add_message(msg)
                    self._send_read_receipt_for_latest()
                    self._refresh_sidebar()

                    # Clear typing indicator for this sender
                    self._typing_users.pop(relay_msg.sender_name, None)
                    status = self.query_one("#status-bar", StatusBar)
                    status.set_typing_indicator(list(self._typing_users.keys()))

                    # Auto-respond based on room mode
                    content = relay_msg.content or ""
                    mode = self._group_respond_mode
                    should_respond = False

                    if mode == "humans_only":
                        # Only respond if explicitly @mentioned
                        if self._is_mentioned(content):
                            should_respond = True
                    elif mode == "claude_assists":
                        # Don't respond to remote messages (local sends handled separately)
                        pass
                    elif mode == "full_auto":
                        # Respond to all human messages
                        if relay_msg.sender_type == "human":
                            should_respond = True
                    elif mode == "claude_to_claude":
                        # Respond to everything — human and Claude messages
                        should_respond = True

                    if should_respond and not self._sending:
                        prompt = content
                        preamble = self._build_group_context_preamble()
                        if preamble:
                            prompt = preamble + "\n\n" + content
                        await self._respond_to_group_message(prompt)
                else:
                    # Background: increment unread and refresh sidebar for badge
                    self.store.increment_unread(session_id)
                    self._refresh_sidebar()

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if _is_active():
                self.notify(f"Relay receive error: {exc}", severity="error")

    async def _handle_sync_response(
        self,
        sync_msg: RelayMessage,
        session_id: str,
        client: RelayClient,
        is_active: callable,
    ) -> None:
        """Unpack and process missed messages from a sync_response."""
        if not sync_msg.content:
            return
        try:
            payloads = json.loads(sync_msg.content)
        except (json.JSONDecodeError, TypeError):
            return

        for raw_payload in payloads:
            try:
                relay_msg = RelayMessage.from_json(raw_payload)
            except Exception:
                continue

            # Skip own messages
            if relay_msg.sender_id == client._participant_id:
                continue

            # Dedup: skip messages already seen via live receive
            if relay_msg.message_id and relay_msg.message_id in client._seen_message_ids:
                continue
            if relay_msg.message_id:
                client._seen_message_ids.add(relay_msg.message_id)

            # Decrypt if needed (server stores ciphertext)
            if client._room_key and relay_msg.content and is_encrypted(relay_msg.content):
                try:
                    relay_msg.content = decrypt_content(relay_msg.content, client._room_key)
                except Exception:
                    pass

            # Track seq
            if relay_msg.seq and relay_msg.seq > client._last_seq:
                client._last_seq = relay_msg.seq

            if relay_msg.type == "message":
                msg = Message(
                    role="user" if relay_msg.sender_type == "human" else "assistant",
                    content=relay_msg.content or "",
                    session_id=session_id,
                    sender_name=relay_msg.sender_name,
                    sender_type=relay_msg.sender_type,
                )
                self.store.add_message(msg)
                if is_active():
                    msg_list = self.query_one("#message-list", MessageList)
                    await msg_list.add_message(msg)
                else:
                    self.store.increment_unread(session_id)

            elif relay_msg.type == "edit" and relay_msg.target_message_id:
                target = self.store.get_message(relay_msg.target_message_id)
                if target:
                    from datetime import datetime, timezone as tz
                    target.content = relay_msg.content or ""
                    target.edited_at = datetime.now(tz.utc)
                    self.store.update_message(target)

            elif relay_msg.type == "delete" and relay_msg.target_message_id:
                self.store.soft_delete_message(relay_msg.target_message_id)

        self._refresh_sidebar()

    def _is_mentioned(self, content: str) -> bool:
        """Return True if *content* contains an @mention targeting our Claude.

        Matches any of the following (case-insensitive):
        - ``@<name>'s Claude``  (full form, e.g. "@Ed's Claude")
        - ``@<name>``           (short form, e.g. "@Ed")

        The short form is matched as a whole word so that "@Eddie" does not
        trigger a response meant for "@Ed".
        """
        name = self.config.participant_name
        # Full form first (more specific — no word boundary needed after "Claude")
        full_pattern = re.compile(
            r"@" + re.escape(name) + r"'s\s+claude",
            re.IGNORECASE,
        )
        if full_pattern.search(content):
            return True
        # Short form — require a word boundary after the name so partial names
        # don't match unintentionally.
        short_pattern = re.compile(
            r"@" + re.escape(name) + r"\b",
            re.IGNORECASE,
        )
        return bool(short_pattern.search(content))

    async def _respond_to_group_message(self, content: str) -> None:
        """Invoke our Claude in response to a remote group message.

        Creates a placeholder assistant bubble, streams the response, and
        broadcasts it to the relay room — mirroring the flow in
        ``on_compose_area_submitted`` but triggered by an incoming message.

        This method is a no-op if ``_sending`` is already True (concurrency
        guard: skip rather than queue when multiple messages arrive quickly).
        """
        if self._sending:
            return
        self._sending = True

        claude_name = f"{self.config.participant_name}'s Claude"
        assistant_msg = Message(
            role="assistant",
            content="...",
            session_id=self.session.id,
            sender_name=claude_name,
            sender_type="claude",
        )
        self.store.add_message(assistant_msg)

        msg_list = self.query_one("#message-list", MessageList)
        await msg_list.add_message(assistant_msg)

        # Delegate streaming to the existing worker (handles relay broadcast too)
        self._stream_response(content, assistant_msg, None)

    def _detach_relay_client(self) -> None:
        """Clear the active relay pointers without disconnecting.

        The client and its receive task stay alive in the pool so
        background messages continue to be received and stored.
        """
        self._relay_client = None
        self._relay_receive_task = None

    async def _stop_relay_client(self, session_id: str) -> None:
        """Fully disconnect and remove a specific relay client from the pool."""
        task = self._relay_receive_tasks.pop(session_id, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        client = self._relay_clients.pop(session_id, None)
        if client is not None:
            await client.disconnect()
        # Clear active pointers if they reference this session
        if self._relay_client is client:
            self._relay_client = None
            self._relay_receive_task = None

    async def _stop_all_relay_clients(self) -> None:
        """Disconnect all pooled relay clients. Called on app shutdown."""
        for sid in list(self._relay_clients.keys()):
            await self._stop_relay_client(sid)

    def _on_create_group_dismissed(self, result: dict | None) -> None:
        """Called when CreateGroupScreen is dismissed."""
        if result is None:
            return

        # Capture prior Claude session ID for forking into the group
        prior_claude_id = self.session.claude_session_id

        # Store tunnel handle for cleanup (daemon manages itself)
        self._tunnel_proc = result.get("tunnel_proc")

        session = Session(
            name="Group Chat",
            is_group=True,
            relay_url=result["relay_url"],
            room_id=result["room_id"],
            participant_id=result["participant_id"],
            relay_token=result.get("token"),
            encryption_passphrase=result.get("encryption_passphrase"),
        )
        self.store.create_session(session)
        self.session = session
        self._selected_model = None

        async def _setup():
            msg_list = self.query_one("#message-list", MessageList)
            await msg_list.clear_messages()
            self._update_status()
            self._refresh_sidebar()
            # Fork the prior solo session so Claude carries full context
            await self._start_claude_session(
                resume_id=prior_claude_id, fork=bool(prior_claude_id),
            )
            await self._start_relay_client(session)

        self.app.call_later(_setup)

    def _on_join_group_dismissed(self, result: dict | None) -> None:
        """Called when JoinGroupScreen is dismissed."""
        if result is None:
            return

        # Capture prior Claude session ID for forking into the group
        prior_claude_id = self.session.claude_session_id

        session = Session(
            name="Group Chat",
            is_group=True,
            relay_url=result["relay_url"],
            room_id=result["room_id"],
            participant_id=result["participant_id"],
            relay_token=result.get("token"),
            encryption_passphrase=result.get("encryption_passphrase"),
        )
        self.store.create_session(session)
        self.session = session
        self._selected_model = None

        async def _setup():
            msg_list = self.query_one("#message-list", MessageList)
            await msg_list.clear_messages()
            self._update_status()
            self._refresh_sidebar()
            # Fork the prior solo session so Claude carries full context
            await self._start_claude_session(
                resume_id=prior_claude_id, fork=bool(prior_claude_id),
            )
            await self._start_relay_client(session)

        self.app.call_later(_setup)

    def action_group_menu(self) -> None:
        """Show the Create Group / Join Group picker (Ctrl+G)."""
        from reclawed.screens.group import CreateGroupScreen, JoinGroupScreen
        from reclawed.widgets.group_menu import GroupMenuScreen

        def on_choice(choice: str | None) -> None:
            if choice == "create":
                self.app.push_screen(
                    CreateGroupScreen(config=self.config),
                    self._on_create_group_dismissed,
                )
            elif choice == "join":
                self.app.push_screen(
                    JoinGroupScreen(),
                    self._on_join_group_dismissed,
                )

        self.app.push_screen(GroupMenuScreen(), on_choice)

    def _get_context_window_size(self) -> int:
        """Return the context window size for the current model."""
        model = self._selected_model or self.session.model or "sonnet"
        for key, size in self._CONTEXT_WINDOWS.items():
            if key in model.lower():
                return size
        return 200_000

    @staticmethod
    def _derive_session_name(prompt: str, max_len: int = 40) -> str:
        """Return a short session name derived from the first user message.

        Truncates at a word boundary so the name reads naturally. If the
        prompt is shorter than *max_len* the full text is used (stripped).
        """
        text = prompt.strip()
        # Replace interior newlines with spaces so multi-line prompts read as
        # a single coherent phrase.
        text = " ".join(text.splitlines())
        if len(text) <= max_len:
            return text
        # Walk back from the limit to find a clean word boundary.
        truncated = text[:max_len]
        last_space = truncated.rfind(" ")
        if last_space > 0:
            truncated = truncated[:last_space]
        return truncated + "..."

    @work(thread=False)
    async def _auto_name_session(
        self, session_id: str, first_message: str, fallback_name: str
    ) -> None:
        """Ask Claude (haiku) to generate a short session name in the background."""
        try:
            context = f"Message: {first_message[:500]}"
            await self._run_name_generation(session_id, context, guard_name=fallback_name)
        except Exception:
            pass

    @work(thread=False)
    async def _generate_name_for_session(self, session_id: str) -> None:
        """Generate a name from session messages (triggered via context menu)."""
        try:
            self.notify("Generating name...", timeout=2)
            session = self.store.get_session(session_id)
            messages = self.store.get_session_messages(session_id)
            # Build context from messages + session name
            context_parts: list[str] = []
            # Use the session name as primary context (it's the first user message)
            if session and session.name and session.name not in ("New Chat", "Group Chat"):
                context_parts.append(f"Topic: {session.name}")
            for msg in messages[:6]:
                role = "Human" if msg.role == "user" else "Claude"
                text = msg.content[:200] if msg.content else ""
                # Skip synthetic import messages and encrypted content
                if not text or "Imported session" in text or text.startswith('{"v":'):
                    continue
                context_parts.append(f"{role}: {text}")
            context = "\n".join(context_parts)
            if not context.strip():
                self.notify("No messages to generate name from", severity="warning", timeout=3)
                return
            result = await self._run_name_generation(session_id, context, guard_name=None)
            if result:
                self.notify(f"Renamed to: {result}", timeout=3)
            else:
                self.notify("Could not generate name", severity="warning", timeout=3)
        except Exception as e:
            self.notify(f"Name generation failed: {e}", severity="error", timeout=5)

    async def _run_name_generation(
        self, session_id: str, context: str, guard_name: str | None
    ) -> str | None:
        """Shared logic for generating a session name via haiku.

        Returns the generated name, or None if generation failed.
        Uses --output-format text and suppresses stderr to prevent
        ANSI escape code leakage into the terminal/compose area.
        """
        naming_prompt = (
            "Your ONLY job: output a 3-5 word title for this chat. "
            "Output NOTHING else. No quotes. No explanation. Just the title.\n\n"
            f"{context}\n\n"
            "Title:"
        )
        # Use a direct subprocess with text output and stderr suppressed
        # to avoid ANSI escape codes leaking into the terminal
        import os, sys, subprocess as _sp
        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        _flags = {"creationflags": _sp.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        proc = await asyncio.create_subprocess_exec(
            self.config.claude_binary, "-p", naming_prompt,
            "--output-format", "text",
            "--model", "haiku",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
            **_flags,
        )
        stdout, _ = await proc.communicate()
        generated_name = stdout.decode("utf-8", errors="replace").strip() if stdout else None

        if not generated_name:
            return None

        # Clean up the result
        cleaned = generated_name.strip().strip('"\'').strip()
        cleaned = cleaned.rstrip(".")
        # Take only the first line in case haiku added explanation
        cleaned = cleaned.split("\n")[0].strip()
        # Truncate to 50 chars at word boundary if too long
        if len(cleaned) > 50:
            truncated = cleaned[:50]
            last_space = truncated.rfind(" ")
            if last_space > 10:
                cleaned = truncated[:last_space]
            else:
                cleaned = truncated
        if not cleaned or len(cleaned) < 3:
            return None

        # Race-condition guard: for auto-naming, only update if name unchanged
        session = self.store.get_session(session_id)
        if not session:
            return None
        if guard_name is not None and session.name != guard_name:
            return None

        session.name = cleaned
        self.store.update_session(session)

        def _apply_name() -> None:
            if self.session.id == session_id:
                self.session.name = cleaned
                self._update_status()
            self._refresh_sidebar()

        self.app.call_later(_apply_name)
        return cleaned

    @work(thread=False)
    async def _stream_response(
        self, prompt: str, assistant_msg: Message, reply_context: str | None
    ) -> None:
        # Capture context at start so session switches don't confuse us
        stream_session = self.session
        stream_claude = self._claude
        stream_relay = self._relay_client
        msg_list = self.query_one("#message-list", MessageList)
        bubble = msg_list.get_bubble(assistant_msg.id)
        content_parts: list[str] = []

        def _is_active() -> bool:
            """Check if this stream's session is still the visible one."""
            return self.session.id == stream_session.id

        status = self.query_one("#status-bar", StatusBar)
        if _is_active():
            status.set_streaming(active=True)

        token_count = 0
        stream_start: float | None = None
        last_render: float = 0.0
        throttle_s = self.config.stream_throttle_ms / 1000.0

        try:
            if stream_claude is None:
                raise RuntimeError("Claude session not initialized")
            async for event in stream_claude.send_message(
                prompt,
                session_id=stream_session.claude_session_id,
                reply_context=reply_context,
                model=self._selected_model,
            ):
                if isinstance(event, StreamSessionId):
                    stream_session.claude_session_id = event.session_id
                    assistant_msg.claude_session_id = event.session_id
                    self.store.update_session(stream_session)

                elif isinstance(event, StreamToken):
                    if stream_start is None:
                        stream_start = time.monotonic()
                    token_count += len(event.text.split())

                    content_parts.append(event.text)
                    now = time.monotonic()

                    # Only update UI if this session is still visible
                    if _is_active():
                        elapsed = now - stream_start
                        status.set_streaming(tokens=token_count, elapsed=elapsed, active=True)
                        if bubble and (now - last_render) >= throttle_s:
                            last_render = now
                            bubble.update_content("".join(content_parts))
                            msg_list.scroll_end(animate=False)

                elif isinstance(event, StreamToolUse):
                    if _is_active() and bubble:
                        bubble.add_tool_use(
                            event.tool_use_id, event.tool_name, event.tool_input,
                        )
                        # AskUserQuestion: render choices as clickable buttons
                        if event.tool_name == "AskUserQuestion":
                            questions = event.tool_input.get("questions", [])
                            if questions:
                                from reclawed.widgets.ask_user_question import AskUserQuestionWidget
                                try:
                                    await bubble.mount(AskUserQuestionWidget(questions))
                                except Exception:
                                    pass
                        msg_list.scroll_end(animate=False)

                elif isinstance(event, StreamToolResult):
                    if _is_active() and bubble:
                        bubble.complete_tool(
                            event.tool_use_id, event.content, event.is_error,
                        )

                elif isinstance(event, StreamResult):
                    assistant_msg.content = event.content or "".join(content_parts)
                    assistant_msg.cost_usd = event.cost_usd
                    assistant_msg.duration_ms = event.duration_ms
                    assistant_msg.model = event.model
                    assistant_msg.input_tokens = event.input_tokens
                    assistant_msg.output_tokens = event.output_tokens
                    if event.session_id:
                        assistant_msg.claude_session_id = event.session_id
                        stream_session.claude_session_id = event.session_id

                    self.store.update_message(assistant_msg)

                    if event.cost_usd:
                        stream_session.total_cost_usd += event.cost_usd
                    if event.model:
                        stream_session.model = event.model
                    stream_session.message_count = len(
                        self.store.get_session_messages(stream_session.id)
                    )
                    was_unnamed = stream_session.name in ("New Chat", "Group Chat")
                    if was_unnamed:
                        stream_session.name = self._derive_session_name(prompt)
                    # Fire background auto-naming after first exchange
                    if was_unnamed and self.config.auto_name_sessions:
                        self._auto_name_session(
                            stream_session.id,
                            prompt,
                            self._derive_session_name(prompt),
                        )
                    # Update context gauge
                    if event.input_tokens:
                        stream_session.last_input_tokens = event.input_tokens
                    self.store.update_session(stream_session)

                    if _is_active() and event.input_tokens:
                        ctx_max = self._get_context_window_size()
                        status.set_context(event.input_tokens, ctx_max)

                    # Broadcast in group chat
                    if stream_session.is_group and stream_relay is not None:
                        try:
                            self._pending_echo_ids.append(assistant_msg.id)
                            claude_label = f"{self.config.participant_name}'s Claude"
                            await stream_relay.send_message(
                                assistant_msg.content,
                                sender_type="claude",
                                sender_name_override=claude_label,
                            )
                        except Exception:
                            pass

                    # Update UI only if still the active session
                    if _is_active():
                        final_tokens = event.output_tokens or token_count
                        final_elapsed = (
                            (time.monotonic() - stream_start) if stream_start else None
                        )
                        status.set_streaming(
                            tokens=final_tokens, elapsed=final_elapsed, active=True
                        )
                        if bubble:
                            await bubble.finalize_content(assistant_msg.content)
                            msg_list.scroll_end(animate=False)
                    else:
                        # Background session got a response — bump unread
                        self.store.increment_unread(stream_session.id)
                        self._refresh_sidebar()

                elif isinstance(event, StreamError):
                    assistant_msg.content = f"Error: {event.message}"
                    self.store.update_message(assistant_msg)
                    if _is_active() and bubble:
                        await bubble.finalize_content(assistant_msg.content)

        except asyncio.CancelledError:
            if stream_claude:
                stream_claude.cancel()
            raise

        except Exception as e:
            assistant_msg.content = f"Error: {e}"
            self.store.update_message(assistant_msg)
            if _is_active() and bubble:
                bubble.update_content(assistant_msg.content)

        finally:
            self._sending = False
            if _is_active():
                try:
                    compose = self.query_one("#compose-area", ComposeArea)
                    compose.set_enabled(True)
                    compose.query_one("#compose-input").focus()
                except Exception:
                    pass

            # Keep the final tok/s visible for 3 seconds, then revert.
            def _clear_streaming_indicator() -> None:
                if _is_active():
                    status.set_streaming(active=False)
                    self._update_status()
                self._refresh_sidebar()

            self.set_timer(3.0, _clear_streaming_indicator)

    # --- Selection & interaction ---

    @property
    def _compose_focused(self) -> bool:
        """Check if the compose TextArea currently has focus."""
        focused = self.app.focused
        if focused is None:
            return False
        try:
            compose_input = self.query_one("#compose-input")
            return focused is compose_input
        except Exception:
            return False

    def on_message_bubble_selected(self, event: MessageBubble.Selected) -> None:
        msg_list = self.query_one("#message-list", MessageList)
        msg_list.select_message(event.message_id)

    def on_message_bubble_reply_clicked(self, event: MessageBubble.ReplyClicked) -> None:
        """Scroll to and highlight the original message when a reply indicator is clicked."""
        msg_list = self.query_one("#message-list", MessageList)
        bubble = msg_list.get_bubble(event.reply_to_id)
        if bubble is None:
            self.notify("Original message not found", severity="warning")
            return
        msg_list.select_message(event.reply_to_id)

    def action_select_prev(self) -> None:
        if self._compose_focused:
            return
        msg_list = self.query_one("#message-list", MessageList)
        msg_list.select_prev()

    def action_select_next(self) -> None:
        if self._compose_focused:
            return
        msg_list = self.query_one("#message-list", MessageList)
        msg_list.select_next()

    def action_toggle_focus(self) -> None:
        """Toggle focus between compose area and message navigation."""
        if self._compose_focused:
            # Switch to navigation mode — focus the message list
            msg_list = self.query_one("#message-list", MessageList)
            msg_list.focus()
            # Auto-select last message if nothing selected
            if msg_list.selected_id is None:
                msg_list.select_prev()
            self.notify("Navigate mode: use arrows, r/q/b/c. Tab or Esc to type.", timeout=3)
        else:
            # Switch back to compose
            self.query_one("#compose-input").focus()

    def action_deselect(self) -> None:
        msg_list = self.query_one("#message-list", MessageList)
        msg_list.select_message(None)
        quote_preview = self.query_one("#quote-preview", QuotePreview)
        quote_preview.hide()
        # Return focus to compose
        self.query_one("#compose-input").focus()

    def action_reply(self) -> None:
        if self._compose_focused:
            return
        msg_list = self.query_one("#message-list", MessageList)
        selected = msg_list.get_selected_message()
        if selected:
            quote_preview = self.query_one("#quote-preview", QuotePreview)
            quote_preview.show_reply(selected.id, selected.content)
            compose = self.query_one("#compose-area", ComposeArea)
            compose.query_one("#compose-input").focus()
            self.notify(f"Replying to: {selected.content[:60]}...")

    def action_quote(self) -> None:
        if self._compose_focused:
            return
        msg_list = self.query_one("#message-list", MessageList)
        selected = msg_list.get_selected_message()
        if selected:
            compose = self.query_one("#compose-area", ComposeArea)
            compose.insert_quote(selected.content)

    def action_bookmark(self) -> None:
        if self._compose_focused:
            return
        msg_list = self.query_one("#message-list", MessageList)
        selected = msg_list.get_selected_message()
        if selected:
            selected.bookmarked = not selected.bookmarked
            self.store.update_message(selected)
            bubble = msg_list.get_bubble(selected.id)
            if bubble:
                bubble.update_content(selected.content)
            state = "bookmarked" if selected.bookmarked else "unbookmarked"
            self.notify(f"Message {state}")

    def action_copy_message(self) -> None:
        if self._compose_focused:
            return
        msg_list = self.query_one("#message-list", MessageList)
        selected = msg_list.get_selected_message()
        if selected:
            if copy_to_clipboard(selected.content):
                self.notify("Copied to clipboard")
            else:
                self.notify("Copy failed — no clipboard tool available", severity="error")

    def action_edit_message(self) -> None:
        """Enter edit mode for the selected message (own messages only)."""
        if self._compose_focused:
            return
        msg_list = self.query_one("#message-list", MessageList)
        selected = msg_list.get_selected_message()
        if not selected:
            return
        if selected.role != "user":
            self.notify("Can only edit your own messages", severity="warning", timeout=3)
            return
        if selected.deleted:
            self.notify("Cannot edit a deleted message", severity="warning", timeout=3)
            return
        compose = self.query_one("#compose-area", ComposeArea)
        compose.start_edit(selected.id, selected.content)

    async def _handle_edit_submit(self, message_id: str, new_content: str) -> None:
        """Edit a user message and regenerate Claude's response."""
        from datetime import datetime, timezone as tz

        if self._sending:
            return

        msg = self.store.get_message(message_id)
        if not msg:
            return

        # 1. Update user message content + edited_at
        msg.content = new_content
        msg.edited_at = datetime.now(tz.utc)
        self.store.update_message(msg)

        msg_list = self.query_one("#message-list", MessageList)

        # 2. Update user bubble in-place
        bubble = msg_list.get_bubble(message_id)
        if bubble:
            bubble.update_content(new_content)
            bubble._message.edited_at = msg.edited_at

        # 3. Find and soft-delete the next assistant message (old Claude reply)
        next_id = msg_list.get_next_message_id(message_id)
        if next_id:
            next_bubble = msg_list.get_bubble(next_id)
            if next_bubble and next_bubble.message.role == "assistant":
                self.store.soft_delete_message(next_id)
                await next_bubble.mark_deleted()

        # 4. Broadcast edit in group chat
        if self.session.is_group and self._relay_client is not None:
            try:
                await self._relay_client.send_edit(message_id, new_content)
            except Exception:
                pass

        # 5. In group sessions with mode "off", skip Claude entirely
        if self.session.is_group and self._group_respond_mode == "humans_only":
            self.notify("Message edited", timeout=2)
            return

        # 6. Create new assistant placeholder and stream fresh response
        self._sending = True
        compose = self.query_one("#compose-area", ComposeArea)
        compose.set_enabled(False)

        prompt = new_content
        if self.session.is_group:
            preamble = self._build_group_context_preamble()
            if preamble:
                prompt = preamble + "\n\n" + prompt

        claude_name = f"{self.config.participant_name}'s Claude" if self.session.is_group else None
        assistant_msg = Message(
            role="assistant",
            content="...",
            session_id=self.session.id,
            sender_name=claude_name,
            sender_type="claude" if self.session.is_group else None,
        )
        self.store.add_message(assistant_msg)
        await msg_list.add_message(assistant_msg)

        self._stream_response(prompt, assistant_msg, None)

    def action_delete_message(self) -> None:
        """Soft-delete the selected message and its Claude reply (own messages only)."""
        if self._compose_focused:
            return
        msg_list = self.query_one("#message-list", MessageList)
        selected = msg_list.get_selected_message()
        if not selected:
            return
        if selected.role != "user":
            self.notify("Can only delete your own messages", severity="warning", timeout=3)
            return
        if selected.deleted:
            return

        # 1. Soft-delete the user message
        selected.deleted = True
        self.store.soft_delete_message(selected.id)
        bubble = msg_list.get_bubble(selected.id)
        if bubble:
            asyncio.create_task(bubble.mark_deleted())

        # 2. Also soft-delete the next assistant message (Claude's reply)
        next_id = msg_list.get_next_message_id(selected.id)
        if next_id:
            next_bubble = msg_list.get_bubble(next_id)
            if next_bubble and next_bubble.message.role == "assistant":
                self.store.soft_delete_message(next_id)
                asyncio.create_task(next_bubble.mark_deleted())

                # Broadcast delete for the reply too
                if self.session.is_group and self._relay_client is not None:
                    try:
                        asyncio.create_task(self._relay_client.send_delete(next_id))
                    except Exception:
                        pass

        # 3. Broadcast delete for the user message
        if self.session.is_group and self._relay_client is not None:
            try:
                asyncio.create_task(self._relay_client.send_delete(selected.id))
            except Exception:
                pass

        self.notify("Message deleted", timeout=2)

    # --- Typing indicators ---

    async def _on_tool_approval_needed(self, tool_name: str, tool_input: dict, future: asyncio.Future) -> None:
        """Called from ClaudeSession's can_use_tool — show approval UI.

        Special handling for AskUserQuestion: renders choices as clickable
        buttons instead of approve/deny.
        """
        from reclawed.widgets.tool_approval import ToolApprovalWidget
        tool_use_id = f"approval-{id(future)}"
        self._pending_approvals[tool_use_id] = future

        # AskUserQuestion: auto-approve (choices rendered at StreamToolUse level)
        if tool_name == "AskUserQuestion":
            if not future.done():
                from claude_agent_sdk import PermissionResultAllow
                future.set_result(PermissionResultAllow())
            return

        try:
            msg_list = self.query_one("#message-list", MessageList)
            # Find the most recent assistant bubble
            bubbles = list(msg_list.query(MessageBubble))
            if bubbles:
                bubble = bubbles[-1]
                widget = ToolApprovalWidget(tool_use_id, tool_name, tool_input)
                bubble.mount(widget)
                msg_list.scroll_end(animate=False)
        except Exception:
            # If UI fails, auto-approve to avoid deadlock
            if not future.done():
                from claude_agent_sdk import PermissionResultAllow
                future.set_result(PermissionResultAllow())

    def on_tool_approval_widget_decided(self, event) -> None:
        """Handle approve/deny from the ToolApprovalWidget."""
        event.stop()
        future = self._pending_approvals.pop(event.tool_use_id, None)
        if future is not None and not future.done():
            if event.approved:
                from claude_agent_sdk import PermissionResultAllow
                future.set_result(PermissionResultAllow())
            else:
                from claude_agent_sdk import PermissionResultDeny
                future.set_result(PermissionResultDeny(message="User denied"))

    def on_choice_buttons_selected(self, event) -> None:
        """Handle choice button click — auto-submit the selection."""
        event.stop()
        self.post_message(ComposeArea.Submitted(f"Option {event.label}: {event.description}"))

    def on_ask_user_question_widget_submitted(self, event) -> None:
        """Handle AskUserQuestion form submission — send all answers."""
        event.stop()
        self.post_message(ComposeArea.Submitted(event.answers))

    def on_compose_area_mention_triggered(self, event: ComposeArea.MentionTriggered) -> None:
        """Show @mention participant picker."""
        event.stop()
        if not self.session.is_group or self._relay_client is None:
            return
        participants = self._relay_client.participants
        if not participants:
            return
        # Build name list (exclude self)
        names = [
            p.get("participant_name", "Unknown")
            for p in participants
            if p.get("participant_id") != self._relay_client._participant_id
        ]
        if not names:
            return
        # Use a simple selection via notification + compose for now
        # If only one other participant, auto-insert
        compose = self.query_one("#compose-area", ComposeArea)
        if len(names) == 1:
            compose.insert_mention(names[0])
        else:
            # Show a quick picker
            from reclawed.screens.search import SessionPickerScreen
            # Reuse a simple approach: push a quick selection
            def _on_pick(name: str | None) -> None:
                if name:
                    compose.insert_mention(name)

            from textual.screen import ModalScreen
            from textual.widgets import Label, ListView, ListItem
            from textual.app import ComposeResult as CR
            from textual.binding import Binding as B

            class _MentionPicker(ModalScreen[str | None]):
                DEFAULT_CSS = """
                _MentionPicker { align: center middle; }
                _MentionPicker > #picker { width: 40; height: auto; max-height: 12;
                    border: thick $primary; background: $surface; padding: 1; }
                """
                BINDINGS = [B("escape", "cancel", priority=True)]

                def compose(self) -> CR:
                    from textual.containers import Vertical
                    with Vertical(id="picker"):
                        yield Label("@mention who?")
                        yield ListView(
                            *[ListItem(Label(n), id=f"m-{i}") for i, n in enumerate(names)]
                        )

                def on_list_view_selected(self, event) -> None:
                    idx = event.list_view.index
                    if idx is not None and 0 <= idx < len(names):
                        self.dismiss(names[idx])

                def action_cancel(self) -> None:
                    self.dismiss(None)

            self.app.push_screen(_MentionPicker(), _on_pick)

    def on_compose_area_typing_started(self, event: ComposeArea.TypingStarted) -> None:
        """Send typing indicator when user types in group chat."""
        if self.session.is_group and self._relay_client is not None:
            asyncio.create_task(self._relay_client.send_typing())

    def _start_typing_timer(self) -> None:
        """Start a 1-second timer to expire stale typing indicators."""
        if self._typing_timer_running:
            return
        self._typing_timer_running = True

        def _check_typing() -> None:
            now = time.monotonic()
            expired = [name for name, ts in self._typing_users.items() if now - ts > 5.0]
            for name in expired:
                del self._typing_users[name]

            status = self.query_one("#status-bar", StatusBar)
            status.set_typing_indicator(list(self._typing_users.keys()))

            if self._typing_users:
                self.set_timer(1.0, _check_typing)
            else:
                self._typing_timer_running = False

        self.set_timer(1.0, _check_typing)

    # --- Read receipts ---

    def _send_read_receipt_for_latest(self) -> None:
        """Send a read receipt for the highest seq we've seen."""
        if self._relay_client and self._relay_client._last_seq > 0:
            asyncio.create_task(
                self._relay_client.send_read_receipt(self._relay_client._last_seq)
            )

    def _update_delivery_status(self) -> None:
        """Recompute delivery status for all outgoing bubbles based on read receipts."""
        if not self._read_receipts:
            return
        msg_list = self.query_one("#message-list", MessageList)
        for msg_id, bubble in msg_list._bubbles.items():
            if bubble.message.role != "user" or bubble.message.sender_type != "human":
                continue
            seq = self._msg_id_to_seq.get(msg_id)
            if seq is None:
                continue
            # Check if all other participants have read up to this seq
            all_read = all(v >= seq for v in self._read_receipts.values())
            any_read = any(v >= seq for v in self._read_receipts.values())
            if all_read:
                bubble.set_delivery_status("read")
            elif any_read:
                bubble.set_delivery_status("delivered")
            else:
                bubble.set_delivery_status("sent")

    # --- Connection status callback ---

    def _make_relay_status_callback(self, session_id: str):
        """Return a session-bound status callback for a pooled relay client."""
        def _on_status(status: str, attempt: int) -> None:
            if self.session.id != session_id:
                return  # Don't update UI for background sessions
            try:
                status_bar = self.query_one("#status-bar", StatusBar)
                if status == "connected":
                    status_bar.set_connection_status(None)
                    self._send_read_receipt_for_latest()
                elif status == "reconnecting":
                    status_bar.set_connection_status(f"Reconnecting... (attempt {attempt})")
                elif status == "disconnected":
                    status_bar.set_connection_status("Disconnected")
            except Exception:
                pass
        return _on_status

    # --- Group context preamble ---

    def _build_group_context_preamble(self) -> str:
        """Build a context preamble from recent group messages."""
        messages = self.store.get_session_messages(self.session.id)
        # Take the last N messages (excluding deleted)
        recent = [m for m in messages if not m.deleted]
        window = self.config.group_context_window
        recent = recent[-window:] if len(recent) > window else recent
        if not recent:
            return ""
        lines = ["[Group chat context:]"]
        for msg in recent:
            name = msg.sender_name or ("You" if msg.role == "user" else "Claude")
            # Truncate long messages in context
            content = msg.content[:200]
            if len(msg.content) > 200:
                content += "..."
            lines.append(f"{name}: {content}")
        return "\n".join(lines)

    def action_search(self) -> None:
        if self._compose_focused:
            return
        from reclawed.screens.search import SearchScreen
        self.app.push_screen(SearchScreen(self.store, self.session.id))

    def action_pinned(self) -> None:
        """Open the pinned messages view (Ctrl+B).

        Reuses the search modal pattern but lists only bookmarked messages.
        Selecting an entry scrolls the chat to that message.
        """
        from reclawed.screens.search import PinnedScreen

        def on_pinned_selected(message_id: str | None) -> None:
            if message_id:
                msg_list = self.query_one("#message-list", MessageList)
                # select_message scrolls the bubble into view automatically
                msg_list.select_message(message_id)

        self.app.push_screen(PinnedScreen(self.store, self.session.id), on_pinned_selected)

    def action_cycle_model(self) -> None:
        """Cycle through available models and apply to the current session (F2)."""
        current = self._selected_model
        try:
            idx = self.MODELS.index(current) if current in self.MODELS else -1
        except ValueError:
            idx = -1
        next_model = self.MODELS[(idx + 1) % len(self.MODELS)]
        self._selected_model = next_model
        # Persist on session so it survives reloads
        self.session.model = next_model
        self.store.update_session(self.session)
        # Inform the SDK client of the model switch
        if self._claude:
            self._claude.set_model(next_model)
        self._update_status()
        self.notify(f"Model: {next_model}", timeout=2)

    def action_cycle_permission(self) -> None:
        """Cycle through permission modes (F5).

        Stops the current Claude session and restarts it with
        ``resume=session_id`` and the new permission mode, so Claude
        keeps full context but operates under different permissions.
        """
        current = self._selected_permission
        try:
            idx = self.PERMISSION_MODES.index(current)
        except ValueError:
            idx = -1
        next_mode = self.PERMISSION_MODES[(idx + 1) % len(self.PERMISSION_MODES)]

        # Confirmation for dangerous mode
        if next_mode == "bypassPermissions":
            self.notify(
                "BYPASS PERMISSIONS — Claude has unrestricted access. "
                "Press F5 again to continue cycling.",
                severity="warning",
                timeout=5,
            )

        self._selected_permission = next_mode

        # Persist on session
        self.session.permission_mode = next_mode
        self.store.update_session(self.session)

        # Update status bar immediately (before restart)
        self._update_status()
        label = self.PERMISSION_MODE_LABELS.get(next_mode, next_mode)
        desc = self.PERMISSION_MODE_DESCRIPTIONS.get(next_mode, "")
        self.notify(f"Permissions: {label} — {desc}", timeout=3)

        # Restart the Claude session with new permissions (silently)
        session_key = self.session.id
        old_claude = self._claude_sessions.pop(session_key, None)
        self._claude = None

        async def _restart():
            if old_claude is not None:
                try:
                    old_claude.cancel()
                    await old_claude.stop()
                except Exception:
                    pass
            session = ClaudeSession(
                cli_path=self.config.claude_binary,
                session_id=self.session.claude_session_id,
                model=self._selected_model,
                cwd=self.session.cwd,
                permission_mode=self._selected_permission,
                allowed_tools=self._effective_allowed_tools(self.session.cwd),
                approval_callback=self._on_tool_approval_needed,
            )
            self._claude_sessions[session_key] = session
            self._claude = session
            await session.start()

        self.app.call_later(_restart)

    def action_cycle_respond_mode(self) -> None:
        """Cycle through room modes (F3). Broadcasts to all participants."""
        current = self._group_respond_mode
        try:
            idx = self.ROOM_MODES.index(current)
        except ValueError:
            idx = -1
        next_mode = self.ROOM_MODES[(idx + 1) % len(self.ROOM_MODES)]
        self._group_respond_mode = next_mode

        # Persist on session
        self.session.room_mode = next_mode
        self.store.update_session(self.session)

        # Broadcast to all participants via relay
        if self.session.is_group and self._relay_client is not None:
            asyncio.create_task(self._relay_client.send_room_mode(next_mode))

        self._update_status()
        label = self.ROOM_MODE_LABELS.get(next_mode, next_mode)
        desc = self.ROOM_MODE_DESCRIPTIONS.get(next_mode, "")
        self.notify(f"Room mode: {label} — {desc}", timeout=3)

    def _switch_to_session(self, session_id: str) -> None:
        """Switch the chat panel to a different session.

        The old session's ClaudeSession and RelayClient stay alive in their
        pools so background work continues (streaming, group messages).
        """
        session = self.store.get_session(session_id)
        if not session:
            return
        # Mark the new session as read
        self.store.mark_session_read(session_id)
        self.session = session
        self._selected_model = session.model
        # Reset send state so compose is usable in the new session
        self._sending = False
        # Restore room mode from session (per-room persistence)
        if session.room_mode and session.room_mode in self.ROOM_MODES:
            self._group_respond_mode = session.room_mode
        # Restore permission mode from session
        self._selected_permission = (
            session.permission_mode or self.config.permission_mode
        )

        async def _reload():
            # Detach the active relay pointer (connection stays alive in pool)
            self._detach_relay_client()
            msg_list = self.query_one("#message-list", MessageList)
            await msg_list.clear_messages()
            await self._load_session_messages()
            self._update_status()
            self._refresh_sidebar()
            # Resume the Claude session for this chat
            await self._start_claude_session(resume_id=session.claude_session_id)
            # Reconnect if the new session is a group session
            if session.is_group:
                await self._start_relay_client(session)

        self.app.call_later(_reload)

    def _refresh_sidebar(self) -> None:
        """Refresh the sidebar to reflect current state."""
        try:
            sidebar = self.query_one("#chat-sidebar", ChatSidebar)
            sidebar.refresh_sessions(active_session_id=self.session.id)
        except Exception:
            pass

    # --- Sidebar events ---

    def on_chat_sidebar_session_selected(self, event: ChatSidebar.SessionSelected) -> None:
        if event.session_id != self.session.id:
            self._switch_to_session(event.session_id)

    def on_chat_sidebar_new_chat_requested(self, event: ChatSidebar.NewChatRequested) -> None:
        self.action_new_chat()

    def on_chat_sidebar_new_chat_in_workspace(self, event: ChatSidebar.NewChatInWorkspace) -> None:
        self._new_chat_with_cwd(event.cwd)

    def on_chat_sidebar_session_renamed(self, event: ChatSidebar.SessionRenamed) -> None:
        """Handle session rename from inline edit."""
        session = self.store.get_session(event.session_id)
        if session:
            session.name = event.new_name
            self.store.update_session(session)
            if event.session_id == self.session.id:
                self.session.name = event.new_name
                self._update_status()
            self._refresh_sidebar()
            self.notify(f"Renamed to: {event.new_name}", timeout=2)

    def on_chat_sidebar_context_menu_requested(self, event: ChatSidebar.ContextMenuRequested) -> None:
        from reclawed.widgets.context_menu import (
            ContextMenu, ACTION_MARK_UNREAD, ACTION_MUTE, ACTION_UNMUTE,
            ACTION_ARCHIVE, ACTION_DELETE, ACTION_RENAME, ACTION_GENERATE_NAME,
            ACTION_PIN, ACTION_UNPIN,
        )

        def on_result(result: tuple[str, str] | None) -> None:
            if result is None:
                return
            action, session_id = result
            session = self.store.get_session(session_id)
            if not session:
                return

            if action == ACTION_MARK_UNREAD:
                session.unread_count = max(1, session.unread_count)
                self.store.update_session(session)
            elif action == ACTION_MUTE:
                session.muted = True
                self.store.update_session(session)
            elif action == ACTION_UNMUTE:
                session.muted = False
                self.store.update_session(session)
            elif action == ACTION_ARCHIVE:
                session.archived = True
                self.store.update_session(session)
                if session.id == self.session.id:
                    self.action_new_chat()
            elif action == ACTION_DELETE:
                self.store.delete_session(session_id)
                asyncio.create_task(self._stop_relay_client(session_id))
                if session_id == self.session.id:
                    self.action_new_chat()
            elif action == ACTION_RENAME:
                sidebar = self.query_one("#chat-sidebar", ChatSidebar)
                sidebar.start_rename(session_id)
                return  # Don't refresh — it would destroy the rename Input
            elif action == ACTION_GENERATE_NAME:
                self._generate_name_for_session(session_id)
                return  # Worker handles refresh
            elif action == ACTION_PIN:
                session.pinned = True
                self.store.update_session(session)
            elif action == ACTION_UNPIN:
                session.pinned = False
                self.store.update_session(session)

            self._refresh_sidebar()

        self.app.push_screen(
            ContextMenu(event.session_id, is_muted=event.is_muted, is_pinned=event.is_pinned),
            on_result,
        )

    def on_chat_sidebar_remove_workspace_requested(self, event: ChatSidebar.RemoveWorkspaceRequested) -> None:
        """Handle workspace removal from the sidebar via right-click."""

        def on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            self.config.workspaces = [
                w for w in self.config.workspaces
                if w.expanded_path != event.cwd
            ]
            self.config.save()
            sidebar = self.query_one("#chat-sidebar", ChatSidebar)
            sidebar._workspaces = self.config.workspaces
            sidebar.refresh_sessions(active_session_id=self.session.id)
            self.notify(f"Removed workspace: {event.name}", timeout=3)

        from reclawed.widgets.confirm_screen import ConfirmScreen
        self.app.push_screen(
            ConfirmScreen(
                title="Remove Workspace",
                message=f'Remove "{event.name}" from the sidebar?\nSessions will be kept.',
            ),
            on_confirm,
        )

    def on_chat_sidebar_refresh_workspace_requested(self, event: ChatSidebar.RefreshWorkspaceRequested) -> None:
        """Re-import sessions from Claude Code for a workspace."""
        from reclawed.importer import DiscoveredProject, discover_projects, import_project_sessions

        # Find the matching project in ~/.claude/projects/
        projects = discover_projects()
        matching = [p for p in projects if p.cwd == event.cwd]
        if not matching:
            self.notify(f"No Claude Code project found for {event.name}", severity="warning", timeout=3)
            return

        project = matching[0]
        count = import_project_sessions(project, self.store)
        self._refresh_sidebar()
        if count > 0:
            self.notify(f"Imported {count} new session{'s' if count != 1 else ''} for {event.name}", timeout=3)
        else:
            self.notify(f"No new sessions found for {event.name}", timeout=3)

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#chat-sidebar", ChatSidebar)
        sidebar.toggle_class("hidden")

    def action_invite_to_chat(self) -> None:
        """Upgrade the current 1:1 session into a group chat (Ctrl+I)."""
        if self.session.is_group:
            self.notify("Already in a group chat", severity="warning", timeout=3)
            return
        from reclawed.screens.group import InviteToChatScreen
        self.app.push_screen(
            InviteToChatScreen(config=self.config),
            self._on_invite_dismissed,
        )

    def _on_invite_dismissed(self, result: dict | None) -> None:
        if result is None:
            return

        self._tunnel_proc = result.get("tunnel_proc")

        # Upgrade existing session to group — NO new session, NO fork
        self.session.is_group = True
        self.session.relay_url = result["relay_url"]
        self.session.room_id = result["room_id"]
        self.session.participant_id = result["participant_id"]
        self.session.relay_token = result.get("token")
        self.session.encryption_passphrase = result.get("encryption_passphrase")
        self.session.room_mode = self._group_respond_mode
        self.store.update_session(self.session)

        async def _setup():
            self._update_status()
            self._refresh_sidebar()
            await self._start_relay_client(self.session)

        self.app.call_later(_setup)

    def action_settings(self) -> None:
        from reclawed.screens.settings import SettingsScreen

        def on_settings_dismissed(changed: bool | None) -> None:
            if changed:
                sidebar = self.query_one("#chat-sidebar", ChatSidebar)
                sidebar._workspaces = self.config.workspaces
                sidebar.refresh_sessions(active_session_id=self.session.id)

        self.app.push_screen(
            SettingsScreen(self.config, self.store),
            on_settings_dismissed,
        )

    def action_change_display_name(self) -> None:
        from reclawed.screens.settings import DisplayNameScreen

        def on_dismissed(new_name: str | None) -> None:
            if new_name:
                self.config.participant_name = new_name
                self.config.save()
                self.notify(f"Display name changed to: {new_name}", timeout=2)

        self.app.push_screen(
            DisplayNameScreen(self.config.participant_name),
            on_dismissed,
        )

    def action_new_chat(self) -> None:
        # Ctrl+N creates a chat in the same workspace as the active session
        self._new_chat_with_cwd(self.session.cwd)

    def action_workspace_new_chat(self) -> None:
        """Show a workspace picker, then create a new chat in the selected one (Ctrl+Shift+N)."""
        if not self.config.workspaces:
            self._new_chat_with_cwd(None)
            return

        from reclawed.widgets.workspace_picker import WorkspacePicker, PICK_DEFAULT

        def on_picked(result: str | None) -> None:
            if result is None:
                return  # Cancelled
            self._new_chat_with_cwd(None if result == PICK_DEFAULT else result)

        self.app.push_screen(
            WorkspacePicker(workspaces=self.config.workspaces),
            on_picked,
        )

    def _new_chat_with_cwd(self, cwd: str | None = None) -> None:
        self.session = self._create_new_session(cwd=cwd)
        # Apply workspace overrides for model and permission
        ws = self.config.workspace_for_cwd(cwd)
        self._selected_model = ws.model if ws and ws.model is not None else None
        self._selected_permission = (
            ws.permission_mode
            if ws and ws.permission_mode is not None
            else self.config.permission_mode
        )

        async def _reset():
            msg_list = self.query_one("#message-list", MessageList)
            await msg_list.clear_messages()
            self._update_status()
            self._refresh_sidebar()
            await self._start_claude_session()

        self.app.call_later(_reset)

    def action_quit(self) -> None:
        # Stop all pooled Claude sessions
        for session in self._claude_sessions.values():
            session.cancel()
            asyncio.create_task(session.stop())
        # Disconnect all pooled relay clients (daemon stays running)
        asyncio.create_task(self._stop_all_relay_clients())
        if self._tunnel_proc is not None and self._tunnel_proc.returncode is None:
            self._tunnel_proc.terminate()
        self.app.exit()

    def action_help(self) -> None:
        if self._compose_focused:
            return
        help_text = (
            "Re:Clawed Keybindings\n"
            "---------------------\n"
            "Enter       Send message\n"
            "Shift+Enter New line\n"
            "Tab         Navigate/Type mode\n"
            "Up/Down     Navigate messages\n"
            "r           Reply to selected\n"
            "q           Quote selected\n"
            "b           Bookmark/pin toggle\n"
            "c           Copy to clipboard\n"
            "e           Edit message\n"
            "d           Delete message\n"
            "/           Search messages\n"
            "F2          Cycle model\n"
            "F3          Cycle room mode\n"
            "            (Humans Only/Claude Assists/\n"
            "             Full Auto/C2C)\n"
            "F4          Settings / Import\n"
            "F5          Cycle permissions\n"
            "            (default/acceptEdits/bypass)\n"
            "Ctrl+G      Group chat (Create/Join)\n"
            "Ctrl+I      Invite to group chat\n"
            "Ctrl+P      Pinned messages\n"
            "Ctrl+N      New chat\n"
            "Ctrl+S      Toggle sidebar\n"
            "Ctrl+T      Cycle theme\n"
            "Ctrl+E      Export markdown\n"
            "Ctrl+D/C    Quit\n"
            "Esc         Deselect / cancel\n"
            "?           This help\n"
            "\n"
            "Group respond modes (F3)\n"
            "  own      — respond to your messages\n"
            "  mentions — respond when @mentioned\n"
            "  all      — respond to every human msg\n"
            "  off      — never auto-respond\n"
            "@mention syntax: @<name> or @<name>'s Claude\n"
        )
        self.notify(help_text, title="Help", timeout=10)

    def action_cycle_theme(self) -> None:
        """Cycle to the next available theme and apply it immediately."""
        current = self.config.theme
        try:
            idx = THEME_CYCLE.index(current)
        except ValueError:
            idx = 0
        next_theme = THEME_CYCLE[(idx + 1) % len(THEME_CYCLE)]
        self.config.theme = next_theme
        self.app.theme = THEME_MAP[next_theme]
        self.notify(f"Theme: {next_theme}", timeout=2)

    def action_export_markdown(self) -> None:
        """Export the current session to ~/Desktop/<session-name>.md."""
        markdown = self.store.export_session_markdown(self.session.id)
        if not markdown:
            self.notify("Nothing to export — session is empty.", severity="warning")
            return

        # Build a safe filename from the session name: replace whitespace and
        # special characters with underscores, strip leading/trailing ones.
        safe_name = "".join(
            c if c.isalnum() or c in "-_." else "_"
            for c in self.session.name
        ).strip("_") or "session"
        dest = Path.home() / "Desktop" / f"{safe_name}.md"

        try:
            dest.write_text(markdown, encoding="utf-8")
            self.notify(f"Exported to {dest}", title="Export complete")
        except OSError as exc:
            self.notify(f"Export failed: {exc}", severity="error")

    def on_quote_preview_cancelled(self, event: QuotePreview.Cancelled) -> None:
        pass  # QuotePreview already hides itself
