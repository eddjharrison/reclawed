"""Main chat screen — orchestrates message sending, receiving, and interaction."""

from __future__ import annotations

import asyncio
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

from reclawed.claude import StreamError, StreamResult, StreamSessionId, StreamToken
from reclawed.claude_session import ClaudeSession
from reclawed.config import Config, THEME_CYCLE, THEME_MAP
from reclawed.crypto import derive_room_key
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
        Binding("ctrl+g", "group_menu", "Group", show=True, key_display="^G", priority=True),
        Binding("ctrl+s", "toggle_sidebar", "Sidebar", show=True, priority=True),
        Binding("ctrl+t", "cycle_theme", "Theme", show=True, key_display="^T", priority=True),
        Binding("ctrl+e", "export_markdown", "Export", show=True, key_display="^E", priority=True),
        Binding("ctrl+p", "pinned", "Pinned", show=True, key_display="^P", priority=True),
        Binding("f2", "cycle_model", "Model", show=True, key_display="F2", priority=True),
        Binding("f3", "cycle_respond_mode", "Respond mode", show=True, key_display="F3", priority=True),
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
        # Group chat relay state
        self._relay_client: RelayClient | None = None
        self._relay_server = None  # asyncio.Server handle (host only)
        self._tunnel_proc = None   # cloudflared subprocess
        self._relay_receive_task: asyncio.Task | None = None
        # Runtime group respond mode — loaded from config but NOT persisted to DB.
        # Cycles via F3: "own" → "mentions" → "all" → "off" → "own"
        self._group_respond_mode: str = config.group_auto_respond
        # Typing indicator tracking: {sender_name: monotonic_time}
        self._typing_users: dict[str, float] = {}
        self._typing_timer_running = False
        # Read receipts tracking: {participant_id: highest_seq_read}
        self._read_receipts: dict[str, int] = {}
        # Map local message IDs to relay seqs for read receipt/edit/delete
        self._msg_id_to_seq: dict[str, int] = {}

    def _create_new_session(self) -> Session:
        session = Session()
        self.store.create_session(session)
        return session

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-layout"):
            yield ChatSidebar(self.store, id="chat-sidebar")
            with Vertical(id="chat-panel"):
                yield MessageList(id="message-list")
                yield QuotePreview(id="quote-preview")
                yield ComposeArea(id="compose-area")
        yield StatusBar(id="status-bar")
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
            permission_mode=self.config.permission_mode,
            allowed_tools=self.config.allowed_tools.split(","),
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
        # Auto-reconnect group sessions on startup (non-blocking)
        if self.session.is_group and self.session.relay_url:
            asyncio.create_task(self._try_reconnect_group())

    async def _load_session_messages(self) -> None:
        msg_list = self.query_one("#message-list", MessageList)
        messages = self.store.get_session_messages(self.session.id)
        for msg in messages:
            await msg_list.add_message(msg)

    def _update_status(self) -> None:
        status = self.query_one("#status-bar", StatusBar)
        group_mode = self._group_respond_mode if self.session.is_group else None
        status.update_info(
            session_name=self.session.name,
            model=self.session.model,
            cost=self.session.total_cost_usd,
            message_count=self.session.message_count,
            group_mode=group_mode,
            clear_group_mode=not self.session.is_group,
        )
        status.set_encrypted(bool(self.session.encryption_passphrase))

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
                await self._relay_client.send_message(event.text, sender_type="human")
            except Exception:
                pass  # Best-effort; don't break the local send flow

        # In group sessions with mode "off", skip Claude entirely.
        if self.session.is_group and self._group_respond_mode == "off":
            self._sending = False
            compose = self.query_one("#compose-area", ComposeArea)
            compose.set_enabled(True)
            compose.query_one("#compose-input").focus()
            return

        # Build prompt with optional group context preamble
        prompt = event.text
        if self.session.is_group and self.config.group_context_mode == "shared_history":
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

    async def _start_relay_client(self, session: Session) -> None:
        """Create and connect a RelayClient for the given group session."""
        if session.relay_url is None or session.room_id is None:
            return
        participant_id = session.participant_id or str(uuid.uuid4())
        room_key: bytes | None = None
        if session.encryption_passphrase and session.room_id:
            room_key = derive_room_key(session.encryption_passphrase, session.room_id)
        self._relay_client = RelayClient(
            url=session.relay_url,
            room_id=session.room_id,
            participant_id=participant_id,
            participant_name=self.config.participant_name,
            participant_type="human",
            token=session.relay_token,
            room_key=room_key,
        )
        self._relay_client.set_status_callback(self._on_relay_status)
        try:
            self.notify("Connecting to relay...", timeout=3)
            await self._relay_client.connect(timeout=10.0)
            # Start the background receive loop as an asyncio task (non-blocking)
            self._relay_receive_task = asyncio.create_task(
                self._relay_receive_loop(), name="relay-receive"
            )
            self.notify(f"Connected to group: {session.room_id[:8]}...", timeout=3)
        except TimeoutError:
            self.notify("Relay connection timed out — check the URL and try again", severity="error", timeout=8)
            self._relay_client = None
        except Exception as exc:
            self.notify(f"Relay connect failed: {exc}", severity="error", timeout=8)
            self._relay_client = None

    async def _relay_receive_loop(self) -> None:
        """Background task: receive relay messages and add them to the message list."""
        if self._relay_client is None:
            return
        try:
            async for relay_msg in self._relay_client.receive_messages():
                # Ignore messages sent by this participant (already shown locally)
                if relay_msg.sender_id == self._relay_client._participant_id:
                    continue

                # Handle typing indicators
                if relay_msg.type == "typing":
                    self._typing_users[relay_msg.sender_name] = time.monotonic()
                    status = self.query_one("#status-bar", StatusBar)
                    status.set_typing_indicator(list(self._typing_users.keys()))
                    self._start_typing_timer()
                    continue

                # Handle read receipts
                if relay_msg.type == "read" and relay_msg.read_up_to_seq is not None:
                    self._read_receipts[relay_msg.sender_id] = relay_msg.read_up_to_seq
                    self._update_delivery_status()
                    continue

                # Handle edits from remote participants
                if relay_msg.type == "edit" and relay_msg.target_message_id:
                    # Find the local message matching the target ID
                    target_msg = self.store.get_message(relay_msg.target_message_id)
                    if target_msg:
                        from datetime import datetime, timezone as tz
                        target_msg.content = relay_msg.content or ""
                        target_msg.edited_at = datetime.now(tz.utc)
                        self.store.update_message(target_msg)
                        msg_list = self.query_one("#message-list", MessageList)
                        bubble = msg_list.get_bubble(relay_msg.target_message_id)
                        if bubble:
                            bubble.update_content(target_msg.content)
                            bubble._message.edited_at = target_msg.edited_at
                    continue

                # Handle deletes from remote participants
                if relay_msg.type == "delete" and relay_msg.target_message_id:
                    target_msg = self.store.get_message(relay_msg.target_message_id)
                    if target_msg:
                        self.store.soft_delete_message(relay_msg.target_message_id)
                        msg_list = self.query_one("#message-list", MessageList)
                        bubble = msg_list.get_bubble(relay_msg.target_message_id)
                        if bubble:
                            await bubble.mark_deleted()
                    continue

                # Ignore non-message types (presence/heartbeat/system)
                if relay_msg.type != "message":
                    continue

                msg = Message(
                    role="user" if relay_msg.sender_type == "human" else "assistant",
                    content=relay_msg.content or "",
                    session_id=self.session.id,
                    sender_name=relay_msg.sender_name,
                    sender_type=relay_msg.sender_type,
                )
                self.store.add_message(msg)

                # Track message ID to relay seq for read receipts
                if relay_msg.seq:
                    self._msg_id_to_seq[msg.id] = relay_msg.seq

                msg_list = self.query_one("#message-list", MessageList)
                await msg_list.add_message(msg)

                # Send read receipt for this message
                self._send_read_receipt_for_latest()

                # Increment unread if this isn't the active session
                # (always active here since we have only one chat panel for now)
                self._refresh_sidebar()

                # Clear typing indicator for this sender
                self._typing_users.pop(relay_msg.sender_name, None)
                status = self.query_one("#status-bar", StatusBar)
                status.set_typing_indicator(list(self._typing_users.keys()))

                # Decide whether to have our Claude respond to this remote message.
                # Only act on human messages (not Claude messages from other participants).
                if relay_msg.sender_type == "human":
                    content = relay_msg.content or ""
                    mode = self._group_respond_mode
                    should_respond = False

                    if mode == "all":
                        should_respond = True
                    elif mode == "mentions" and self._is_mentioned(content):
                        should_respond = True

                    if should_respond and not self._sending:
                        # Build prompt with optional group context preamble
                        prompt = content
                        if self.config.group_context_mode == "shared_history":
                            preamble = self._build_group_context_preamble()
                            if preamble:
                                prompt = preamble + "\n\n" + content
                        await self._respond_to_group_message(prompt)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.notify(f"Relay receive error: {exc}", severity="error")

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

    async def _stop_relay_client(self) -> None:
        """Gracefully disconnect the relay client and cancel the receive task."""
        if self._relay_receive_task is not None:
            self._relay_receive_task.cancel()
            try:
                await self._relay_receive_task
            except asyncio.CancelledError:
                pass
            self._relay_receive_task = None
        if self._relay_client is not None:
            await self._relay_client.disconnect()
            self._relay_client = None

    def _on_create_group_dismissed(self, result: dict | None) -> None:
        """Called when CreateGroupScreen is dismissed."""
        if result is None:
            return

        # Capture prior Claude session ID for forking into the group
        prior_claude_id = self.session.claude_session_id

        # Store handles for cleanup
        self._relay_server = result.get("relay_server")
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
                    CreateGroupScreen(port=self.config.relay_port),
                    self._on_create_group_dismissed,
                )
            elif choice == "join":
                self.app.push_screen(
                    JoinGroupScreen(),
                    self._on_join_group_dismissed,
                )

        self.app.push_screen(GroupMenuScreen(), on_choice)

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
    async def _stream_response(
        self, prompt: str, assistant_msg: Message, reply_context: str | None
    ) -> None:
        # Capture context at start so session switches don't confuse us
        stream_session = self.session
        stream_claude = self._claude
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
                    if stream_session.name in ("New Chat", "Group Chat"):
                        stream_session.name = self._derive_session_name(prompt)
                    self.store.update_session(stream_session)

                    # Broadcast in group chat
                    if stream_session.is_group and self._relay_client is not None:
                        try:
                            claude_label = f"{self.config.participant_name}'s Claude"
                            await self._relay_client.send_message(
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
        if self.session.is_group and self._group_respond_mode == "off":
            self.notify("Message edited", timeout=2)
            return

        # 6. Create new assistant placeholder and stream fresh response
        self._sending = True
        compose = self.query_one("#compose-area", ComposeArea)
        compose.set_enabled(False)

        prompt = new_content
        if self.session.is_group and self.config.group_context_mode == "shared_history":
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

    def _on_relay_status(self, status: str, attempt: int) -> None:
        """Called by RelayClient on connection state changes."""
        try:
            status_bar = self.query_one("#status-bar", StatusBar)
            if status == "connected":
                status_bar.set_connection_status(None)
                # Send read receipt on reconnect
                self._send_read_receipt_for_latest()
            elif status == "reconnecting":
                status_bar.set_connection_status(f"Reconnecting... (attempt {attempt})")
            elif status == "disconnected":
                status_bar.set_connection_status("Disconnected")
        except Exception:
            pass

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

    # Ordered cycle for F3 respond-mode toggle.
    RESPOND_MODES = ["own", "mentions", "all", "off"]

    def action_cycle_respond_mode(self) -> None:
        """Cycle through group chat respond modes (F3).

        Modes:
          own      — Claude responds only to your own messages (default)
          mentions — Claude responds when @mentioned
          all      — Claude responds to every human message
          off      — Claude never responds automatically
        """
        current = self._group_respond_mode
        try:
            idx = self.RESPOND_MODES.index(current)
        except ValueError:
            idx = -1
        next_mode = self.RESPOND_MODES[(idx + 1) % len(self.RESPOND_MODES)]
        self._group_respond_mode = next_mode
        self._update_status()
        descriptions = {
            "own": "Responding to your messages only",
            "mentions": "Responding to @mentions",
            "all": "Responding to all human messages",
            "off": "Auto-respond off",
        }
        label = descriptions.get(next_mode, next_mode)
        self.notify(f"Group respond mode: [{next_mode}] — {label}", timeout=3)

    def _switch_to_session(self, session_id: str) -> None:
        """Switch the chat panel to a different session.

        The old session's ClaudeSession stays alive in the pool so any
        in-progress responses continue in the background.
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

        async def _reload():
            # Disconnect from the previous relay (if any) before switching
            await self._stop_relay_client()
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
            ACTION_ARCHIVE, ACTION_DELETE, ACTION_RENAME,
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
                if session_id == self.session.id:
                    self.action_new_chat()
            elif action == ACTION_RENAME:
                sidebar = self.query_one("#chat-sidebar", ChatSidebar)
                sidebar.start_rename(session_id)
                return  # Don't refresh — it would destroy the rename Input

            self._refresh_sidebar()

        self.app.push_screen(
            ContextMenu(event.session_id, is_muted=event.is_muted),
            on_result,
        )

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#chat-sidebar", ChatSidebar)
        sidebar.toggle_class("hidden")

    def action_new_chat(self) -> None:
        self.session = self._create_new_session()
        self._selected_model = None

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
        # Best-effort relay cleanup — fire-and-forget on exit
        if self._relay_client is not None:
            asyncio.create_task(self._stop_relay_client())
        if self._relay_server is not None:
            self._relay_server.close()
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
            "F3          Cycle group respond mode\n"
            "            (own/mentions/all/off)\n"
            "Ctrl+G      Group chat (Create/Join)\n"
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
