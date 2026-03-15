"""Main chat screen — orchestrates message sending, receiving, and interaction."""

from __future__ import annotations

import asyncio
import subprocess
import time
import uuid
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header

from reclawed.claude import ClaudeProcess, StreamError, StreamResult, StreamSessionId, StreamToken
from reclawed.config import Config, THEME_CYCLE, THEME_MAP
from reclawed.models import Message, Session
from reclawed.relay.client import RelayClient
from reclawed.store import Store
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
        # These only work in navigate mode (compose not focused)
        Binding("tab", "toggle_focus", "Navigate/Type", show=True, key_display="Tab"),
        Binding("up", "select_prev", "Prev msg", show=False),
        Binding("down", "select_next", "Next msg", show=False),
        Binding("r", "reply", "Reply", show=True, key_display="r"),
        Binding("q", "quote", "Quote", show=True, key_display="q"),
        Binding("b", "bookmark", "Bookmark", show=True, key_display="b"),
        Binding("c", "copy_message", "Copy", show=True, key_display="c"),
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
        self._claude = ClaudeProcess(config.claude_binary)
        self._sending = False
        # Restore the model stored on the session, or start with no override
        # (None means the CLI will use its own default).
        self._selected_model: str | None = self.session.model
        # Group chat relay state
        self._relay_client: RelayClient | None = None
        self._relay_server = None  # asyncio.Server handle (host only)
        self._tunnel_proc = None   # cloudflared subprocess
        self._relay_receive_task: asyncio.Task | None = None

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

    async def on_mount(self) -> None:
        self._update_status()
        # Highlight the active session in the sidebar
        sidebar = self.query_one("#chat-sidebar", ChatSidebar)
        sidebar.refresh_sessions(active_session_id=self.session.id)
        # Load existing messages if resuming a session
        if self.session.message_count > 0:
            await self._load_session_messages()

    async def _load_session_messages(self) -> None:
        msg_list = self.query_one("#message-list", MessageList)
        messages = self.store.get_session_messages(self.session.id)
        for msg in messages:
            await msg_list.add_message(msg)

    def _update_status(self) -> None:
        status = self.query_one("#status-bar", StatusBar)
        status.update_info(
            session_name=self.session.name,
            model=self.session.model,
            cost=self.session.total_cost_usd,
            message_count=self.session.message_count,
        )

    # --- Message handling ---

    async def on_compose_area_submitted(self, event: ComposeArea.Submitted) -> None:
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

        # Create placeholder assistant message
        assistant_msg = Message(
            role="assistant",
            content="...",
            session_id=self.session.id,
        )
        self.store.add_message(assistant_msg)
        await msg_list.add_message(assistant_msg)

        # Stream response
        self._stream_response(event.text, assistant_msg, reply_context)

    # --- Group chat relay helpers ---

    async def _start_relay_client(self, session: Session) -> None:
        """Create and connect a RelayClient for the given group session."""
        if session.relay_url is None or session.room_id is None:
            return
        participant_id = session.participant_id or str(uuid.uuid4())
        self._relay_client = RelayClient(
            url=session.relay_url,
            room_id=session.room_id,
            participant_id=participant_id,
            participant_name=self.config.participant_name,
            participant_type="human",
            token=None,  # token is embedded in relay_url query params via server config
        )
        try:
            await self._relay_client.connect()
            # Start the background receive loop as an asyncio task (non-blocking)
            self._relay_receive_task = asyncio.create_task(
                self._relay_receive_loop(), name="relay-receive"
            )
            self.notify(f"Connected to group: {session.room_id[:8]}...", timeout=3)
        except Exception as exc:
            self.notify(f"Relay connect failed: {exc}", severity="error")
            self._relay_client = None

    async def _relay_receive_loop(self) -> None:
        """Background task: receive relay messages and add them to the message list."""
        if self._relay_client is None:
            return
        try:
            async for relay_msg in self._relay_client.receive_messages():
                # Ignore presence/heartbeat/system messages
                if relay_msg.type != "message":
                    continue
                # Ignore messages sent by this participant (already shown locally)
                if relay_msg.sender_id == self._relay_client._participant_id:
                    continue

                msg = Message(
                    role="user" if relay_msg.sender_type == "human" else "assistant",
                    content=relay_msg.content or "",
                    session_id=self.session.id,
                    sender_name=relay_msg.sender_name,
                    sender_type=relay_msg.sender_type,
                )
                self.store.add_message(msg)

                msg_list = self.query_one("#message-list", MessageList)
                await msg_list.add_message(msg)

                # Increment unread if this isn't the active session
                # (always active here since we have only one chat panel for now)
                self._refresh_sidebar()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.notify(f"Relay receive error: {exc}", severity="error")

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

        # Store handles for cleanup
        self._relay_server = result.get("relay_server")
        self._tunnel_proc = result.get("tunnel_proc")

        session = Session(
            name="Group Chat",
            is_group=True,
            relay_url=result["relay_url"],
            room_id=result["room_id"],
            participant_id=result["participant_id"],
        )
        self.store.create_session(session)
        self.session = session
        self._claude = ClaudeProcess(self.config.claude_binary)
        self._selected_model = None

        async def _setup():
            msg_list = self.query_one("#message-list", MessageList)
            await msg_list.clear_messages()
            self._update_status()
            self._refresh_sidebar()
            await self._start_relay_client(session)

        self.app.call_later(_setup)

    def _on_join_group_dismissed(self, result: dict | None) -> None:
        """Called when JoinGroupScreen is dismissed."""
        if result is None:
            return

        session = Session(
            name="Group Chat",
            is_group=True,
            relay_url=result["relay_url"],
            room_id=result["room_id"],
            participant_id=result["participant_id"],
        )
        self.store.create_session(session)
        self.session = session
        self._claude = ClaudeProcess(self.config.claude_binary)
        self._selected_model = None

        async def _setup():
            msg_list = self.query_one("#message-list", MessageList)
            await msg_list.clear_messages()
            self._update_status()
            self._refresh_sidebar()
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

    @work(exclusive=True, thread=False)
    async def _stream_response(
        self, prompt: str, assistant_msg: Message, reply_context: str | None
    ) -> None:
        msg_list = self.query_one("#message-list", MessageList)
        bubble = msg_list.get_bubble(assistant_msg.id)
        content_parts: list[str] = []

        status = self.query_one("#status-bar", StatusBar)
        # Show "Claude is thinking..." while waiting for the first token.
        status.set_streaming(active=True)

        token_count = 0
        stream_start: float | None = None  # set on receipt of first StreamToken

        try:
            async for event in self._claude.send_message(
                prompt,
                session_id=self.session.claude_session_id,
                reply_context=reply_context,
                model=self._selected_model,
            ):
                if isinstance(event, StreamSessionId):
                    self.session.claude_session_id = event.session_id
                    assistant_msg.claude_session_id = event.session_id
                    self.store.update_session(self.session)

                elif isinstance(event, StreamToken):
                    if stream_start is None:
                        stream_start = time.monotonic()
                    token_count += len(event.text.split())
                    elapsed = time.monotonic() - stream_start
                    status.set_streaming(tokens=token_count, elapsed=elapsed, active=True)

                    content_parts.append(event.text)
                    if bubble:
                        bubble.update_content("".join(content_parts))

                elif isinstance(event, StreamResult):
                    assistant_msg.content = event.content or "".join(content_parts)
                    assistant_msg.cost_usd = event.cost_usd
                    assistant_msg.duration_ms = event.duration_ms
                    assistant_msg.model = event.model
                    assistant_msg.input_tokens = event.input_tokens
                    assistant_msg.output_tokens = event.output_tokens
                    if event.session_id:
                        assistant_msg.claude_session_id = event.session_id
                        self.session.claude_session_id = event.session_id

                    self.store.update_message(assistant_msg)

                    if event.cost_usd:
                        self.session.total_cost_usd += event.cost_usd
                    if event.model:
                        self.session.model = event.model
                    self.session.message_count = len(
                        self.store.get_session_messages(self.session.id)
                    )
                    # Auto-name the session after the first assistant response.
                    if self.session.name in ("New Chat", "Group Chat"):
                        self.session.name = self._derive_session_name(prompt)
                    self.store.update_session(self.session)

                    # In a group session, broadcast Claude's final response so
                    # all participants can see it.
                    if self.session.is_group and self._relay_client is not None:
                        try:
                            await self._relay_client.send_message(
                                assistant_msg.content, sender_type="claude"
                            )
                        except Exception:
                            pass  # Best-effort; don't break the local UI

                    # Prefer the authoritative output_tokens from the result over
                    # our word-count approximation for the final tok/s display.
                    final_tokens = event.output_tokens or token_count
                    final_elapsed = (
                        (time.monotonic() - stream_start) if stream_start else None
                    )
                    status.set_streaming(
                        tokens=final_tokens, elapsed=final_elapsed, active=True
                    )

                    # Re-render the final bubble with metadata
                    if bubble:
                        bubble.update_content(assistant_msg.content)

                elif isinstance(event, StreamError):
                    assistant_msg.content = f"Error: {event.message}"
                    self.store.update_message(assistant_msg)
                    if bubble:
                        bubble.update_content(assistant_msg.content)

        except asyncio.CancelledError:
            self._claude.cancel()
            raise

        except Exception as e:
            assistant_msg.content = f"Error: {e}"
            self.store.update_message(assistant_msg)
            if bubble:
                bubble.update_content(assistant_msg.content)

        finally:
            self._claude.cancel()  # Ensure subprocess is terminated
            self._sending = False
            compose = self.query_one("#compose-area", ComposeArea)
            compose.set_enabled(True)
            compose.query_one("#compose-input").focus()

            # Keep the final tok/s visible for 3 seconds, then revert to normal.
            def _clear_streaming_indicator() -> None:
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
            try:
                proc = subprocess.run(
                    ["pbcopy"], input=selected.content.encode(), check=True,
                )
                self.notify("Copied to clipboard")
            except (FileNotFoundError, subprocess.CalledProcessError):
                try:
                    proc = subprocess.run(
                        ["xclip", "-selection", "clipboard"],
                        input=selected.content.encode(), check=True,
                    )
                    self.notify("Copied to clipboard")
                except Exception:
                    self.notify("Copy failed — pbcopy/xclip not available", severity="error")

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
        """Cycle through available models and apply to the current session (Ctrl+M)."""
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
        self._update_status()
        self.notify(f"Model: {next_model}", timeout=2)

    def _switch_to_session(self, session_id: str) -> None:
        """Switch the chat panel to a different session."""
        session = self.store.get_session(session_id)
        if not session:
            return
        # Mark the new session as read
        self.store.mark_session_read(session_id)
        self.session = session
        self._claude = ClaudeProcess(self.config.claude_binary)
        self._selected_model = session.model

        async def _reload():
            # Disconnect from the previous relay (if any) before switching
            await self._stop_relay_client()
            msg_list = self.query_one("#message-list", MessageList)
            await msg_list.clear_messages()
            await self._load_session_messages()
            self._update_status()
            self._refresh_sidebar()
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
                self.notify("Rename: type new name in sidebar search then press Enter", timeout=5)

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
        self._claude = ClaudeProcess(self.config.claude_binary)
        self._selected_model = None

        async def _reset():
            msg_list = self.query_one("#message-list", MessageList)
            await msg_list.clear_messages()
            self._update_status()
            self._refresh_sidebar()

        self.app.call_later(_reset)

    def action_quit(self) -> None:
        self._claude.cancel()
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
            "/           Search messages\n"
            "F2          Cycle model\n"
            "Ctrl+G      Group chat (Create/Join)\n"
            "Ctrl+P      Pinned messages\n"
            "Ctrl+N      New chat\n"
            "Ctrl+S      Toggle sidebar\n"
            "Ctrl+T      Cycle theme\n"
            "Ctrl+E      Export markdown\n"
            "Ctrl+D/C    Quit\n"
            "Esc         Deselect / cancel\n"
            "?           This help\n"
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
