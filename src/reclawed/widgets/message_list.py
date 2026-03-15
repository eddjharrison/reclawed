"""Scrollable message list container."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive

from reclawed.models import Message
from reclawed.widgets.message_bubble import MessageBubble


class MessageList(VerticalScroll):
    """Vertically scrolling list of message bubbles."""

    DEFAULT_CSS = """
    MessageList {
        width: 100%;
        height: 1fr;
        padding: 1 0;
    }
    """

    selected_id: reactive[str | None] = reactive(None)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._bubbles: dict[str, MessageBubble] = {}
        self._order: list[str] = []
        self._reply_previews: dict[str, str] = {}

    def set_reply_preview(self, message_id: str, preview: str) -> None:
        self._reply_previews[message_id] = preview

    async def add_message(self, message: Message) -> MessageBubble:
        """Add a message bubble to the list."""
        reply_preview = self._reply_previews.get(message.id)
        if not reply_preview and message.reply_to_id and message.reply_to_id in self._bubbles:
            parent = self._bubbles[message.reply_to_id].message
            reply_preview = parent.content[:100]

        bubble = MessageBubble(message, reply_preview=reply_preview)
        self._bubbles[message.id] = bubble
        self._order.append(message.id)
        await self.mount(bubble)
        bubble.scroll_visible(animate=False)
        return bubble

    def get_bubble(self, message_id: str) -> MessageBubble | None:
        return self._bubbles.get(message_id)

    def select_message(self, message_id: str | None) -> None:
        """Select a message by ID, deselecting the previous one."""
        if self.selected_id and self.selected_id in self._bubbles:
            self._bubbles[self.selected_id].selected = False
        self.selected_id = message_id
        if message_id and message_id in self._bubbles:
            self._bubbles[message_id].selected = True
            self._bubbles[message_id].scroll_visible()

    def select_next(self) -> str | None:
        """Move selection to the next message."""
        if not self._order:
            return None
        if self.selected_id is None:
            self.select_message(self._order[0])
            return self._order[0]
        try:
            idx = self._order.index(self.selected_id)
            if idx < len(self._order) - 1:
                new_id = self._order[idx + 1]
                self.select_message(new_id)
                return new_id
        except ValueError:
            pass
        return self.selected_id

    def select_prev(self) -> str | None:
        """Move selection to the previous message."""
        if not self._order:
            return None
        if self.selected_id is None:
            self.select_message(self._order[-1])
            return self._order[-1]
        try:
            idx = self._order.index(self.selected_id)
            if idx > 0:
                new_id = self._order[idx - 1]
                self.select_message(new_id)
                return new_id
        except ValueError:
            pass
        return self.selected_id

    def get_selected_message(self) -> Message | None:
        if self.selected_id and self.selected_id in self._bubbles:
            return self._bubbles[self.selected_id].message
        return None

    async def clear_messages(self) -> None:
        """Remove all message bubbles."""
        await self.remove_children()
        self._bubbles.clear()
        self._order.clear()
        self._reply_previews.clear()
        self.selected_id = None
