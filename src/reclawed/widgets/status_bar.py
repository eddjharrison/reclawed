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
        # Group respond mode badge ("own" | "mentions" | "all" | "off" | None)
        self._group_mode: str | None = None
        # Typing indicator
        self._typing_indicator: str | None = None
        # Connection status
        self._connection_status: str | None = None
        # Encryption indicator
        self._encrypted: bool = False

    def update_info(
        self,
        session_name: str | None = None,
        model: str | None = None,
        cost: float | None = None,
        message_count: int | None = None,
        group_mode: str | None = None,
        clear_group_mode: bool = False,
    ) -> None:
        """Update one or more status bar fields.

        Parameters
        ----------
        group_mode:
            Pass a mode string ("own"/"mentions"/"all"/"off") to display a
            ``[mode]`` badge when in a group session.  Pass ``None`` to leave
            the current badge unchanged.
        clear_group_mode:
            Pass ``True`` to explicitly remove the group mode badge (e.g. when
            leaving a group session).
        """
        if session_name is not None:
            self._session_name = session_name
        if model is not None:
            self._model = model
        if cost is not None:
            self._cost = cost
        if message_count is not None:
            self._message_count = message_count
        if clear_group_mode:
            self._group_mode = None
        elif group_mode is not None:
            self._group_mode = group_mode
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

    def set_typing_indicator(self, names: list[str]) -> None:
        """Show typing indicator for the given user names."""
        if not names:
            self._typing_indicator = None
        elif len(names) == 1:
            self._typing_indicator = f"{names[0]} is typing..."
        else:
            self._typing_indicator = f"{', '.join(names)} are typing..."
        self._refresh_display()

    def set_connection_status(self, status: str | None) -> None:
        """Set connection status text (e.g. 'Reconnecting... (attempt 2)')."""
        self._connection_status = status
        self._refresh_display()

    def set_encrypted(self, encrypted: bool) -> None:
        """Show or hide the encryption lock indicator."""
        self._encrypted = encrypted
        self._refresh_display()

    def _refresh_display(self) -> None:
        parts = [f"Re:Clawed | {self._session_name}"]
        if self._encrypted:
            parts.append("Encrypted")
        if self._group_mode is not None:
            parts.append(f"[{self._group_mode}]")
        if self._connection_status:
            parts.append(self._connection_status)
        if self._typing_indicator:
            parts.append(self._typing_indicator)
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
