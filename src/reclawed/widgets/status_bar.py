"""Status bar showing model, cost, and session info."""

from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """Bottom status bar with session metadata."""

    DEFAULT_CSS = """
    StatusBar {
        width: 100%;
        height: 1;
        dock: bottom;
        background: $primary;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("Re:Clawed | New Chat", **kwargs)
        self._session_name = "New Chat"
        self._model = ""
        self._cost = 0.0
        self._message_count = 0
        # Streaming state: None = idle, "thinking" = waiting, float = tok/s
        self._streaming_indicator: str | None = None

    def update_info(
        self,
        session_name: str | None = None,
        model: str | None = None,
        cost: float | None = None,
        message_count: int | None = None,
    ) -> None:
        if session_name is not None:
            self._session_name = session_name
        if model is not None:
            self._model = model
        if cost is not None:
            self._cost = cost
        if message_count is not None:
            self._message_count = message_count
        self._refresh_display()

    def set_streaming(
        self,
        tokens: int | None = None,
        elapsed: float | None = None,
        active: bool = True,
    ) -> None:
        """Update the streaming indicator in the status bar.

        Call with active=True and no tokens/elapsed to show "Claude is thinking...".
        Call with tokens and elapsed (both > 0) to show a live tok/s rate.
        Call with active=False to clear the streaming indicator.
        """
        if not active:
            self._streaming_indicator = None
        elif tokens is not None and elapsed is not None and elapsed > 0 and tokens > 0:
            rate = tokens / elapsed
            self._streaming_indicator = f"{rate:.0f} tok/s"
        else:
            self._streaming_indicator = "Claude is thinking..."
        self._refresh_display()

    def _refresh_display(self) -> None:
        parts = [f"Re:Clawed | {self._session_name}"]
        if self._streaming_indicator:
            parts.append(self._streaming_indicator)
        else:
            if self._model:
                parts.append(self._model)
            if self._message_count:
                parts.append(f"{self._message_count} msgs")
            if self._cost > 0:
                parts.append(f"${self._cost:.4f}")
        parts.append("? for help")
        self.update(" | ".join(parts))
