"""Main chat screen — orchestrates message sending, receiving, and interaction."""

from __future__ import annotations

import asyncio
import subprocess

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header

from reclawed.claude import ClaudeProcess, StreamError, StreamResult, StreamSessionId, StreamToken
from reclawed.config import Config
from reclawed.models import Message, Session
from reclawed.store import Store
from reclawed.widgets.compose_area import ComposeArea
from reclawed.widgets.message_bubble import MessageBubble
from reclawed.widgets.message_list import MessageList
from reclawed.widgets.quote_preview import QuotePreview
from reclawed.widgets.status_bar import StatusBar


class ChatScreen(Screen):
    """Main chat screen."""

    BINDINGS = [
        Binding("tab", "toggle_focus", "Navigate/Type", show=True, key_display="Tab"),
        Binding("up", "select_prev", "Prev msg", show=False),
        Binding("down", "select_next", "Next msg", show=False),
        Binding("r", "reply", "Reply", show=True, key_display="r"),
        Binding("q", "quote", "Quote", show=True, key_display="q"),
        Binding("b", "bookmark", "Bookmark", show=True, key_display="b"),
        Binding("c", "copy_message", "Copy", show=True, key_display="c"),
        Binding("slash", "search", "Search", show=True, key_display="/"),
        Binding("ctrl+n", "new_chat", "New Chat", show=True),
        Binding("ctrl+s", "sessions", "Sessions", show=True),
        Binding("escape", "deselect", "Back to compose", show=False),
        Binding("question_mark", "help", "Help", show=True, key_display="?"),
    ]

    def __init__(self, store: Store, config: Config, session: Session | None = None) -> None:
        super().__init__()
        self.store = store
        self.config = config
        self.session = session or self._create_new_session()
        self._claude = ClaudeProcess(config.claude_binary)
        self._sending = False

    def _create_new_session(self) -> Session:
        session = Session()
        self.store.create_session(session)
        return session

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield MessageList(id="message-list")
        yield QuotePreview(id="quote-preview")
        yield ComposeArea(id="compose-area")
        yield StatusBar(id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        self._update_status()
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
        )
        self.store.add_message(user_msg)

        msg_list = self.query_one("#message-list", MessageList)
        await msg_list.add_message(user_msg)

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

    @work(exclusive=True, thread=False)
    async def _stream_response(
        self, prompt: str, assistant_msg: Message, reply_context: str | None
    ) -> None:
        msg_list = self.query_one("#message-list", MessageList)
        bubble = msg_list.get_bubble(assistant_msg.id)
        content_parts: list[str] = []

        try:
            async for event in self._claude.send_message(
                prompt,
                session_id=self.session.claude_session_id,
                reply_context=reply_context,
            ):
                if isinstance(event, StreamSessionId):
                    self.session.claude_session_id = event.session_id
                    assistant_msg.claude_session_id = event.session_id
                    self.store.update_session(self.session)

                elif isinstance(event, StreamToken):
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
                    self.store.update_session(self.session)

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
            self._update_status()

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

    def action_new_chat(self) -> None:
        self.session = self._create_new_session()
        self._claude = ClaudeProcess(self.config.claude_binary)

        async def _reset():
            msg_list = self.query_one("#message-list", MessageList)
            await msg_list.clear_messages()
            self._update_status()

        self.app.call_later(_reset)

    def action_sessions(self) -> None:
        from reclawed.screens.sessions import SessionPickerScreen

        def on_session_selected(session_id: str | None) -> None:
            if session_id:
                session = self.store.get_session(session_id)
                if session:
                    self.session = session
                    self._claude = ClaudeProcess(self.config.claude_binary)

                    async def _reload():
                        msg_list = self.query_one("#message-list", MessageList)
                        await msg_list.clear_messages()
                        await self._load_session_messages()
                        self._update_status()

                    self.app.call_later(_reload)

        self.app.push_screen(SessionPickerScreen(self.store), on_session_selected)

    def action_help(self) -> None:
        if self._compose_focused:
            return
        help_text = (
            "Re:Clawed Keybindings\n"
            "---------------------\n"
            "Enter       Send message\n"
            "Shift+Enter New line\n"
            "Up/Down     Navigate messages\n"
            "r           Reply to selected\n"
            "q           Quote selected\n"
            "b           Bookmark toggle\n"
            "c           Copy to clipboard\n"
            "/           Search messages\n"
            "Ctrl+N      New chat\n"
            "Ctrl+S      Session picker\n"
            "Esc         Deselect / cancel\n"
            "?           This help\n"
        )
        self.notify(help_text, title="Help", timeout=10)

    def on_quote_preview_cancelled(self, event: QuotePreview.Cancelled) -> None:
        pass  # QuotePreview already hides itself
