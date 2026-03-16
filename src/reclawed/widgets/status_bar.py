"""Minimal status bar — context gauge, model, cost, conditional badges."""

from __future__ import annotations

from textual.widgets import Static

_BAR_WIDTH = 10


def _context_bar(tokens: int, max_tokens: int) -> str:
    """Render a compact progress bar: ████████░░ 78%"""
    if max_tokens <= 0 or tokens <= 0:
        return ""
    pct = min(tokens / max_tokens, 1.0)
    filled = round(pct * _BAR_WIDTH)
    empty = _BAR_WIDTH - filled
    bar = "\u2588" * filled + "\u2591" * empty
    return f"{bar} {pct:.0%}"


class StatusBar(Static):
    """Bottom status bar — clean, minimal, context-aware."""

    DEFAULT_CSS = """
    StatusBar {
        width: 100%;
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("Re:Clawed | New Chat", **kwargs)
        self._session_name = "New Chat"
        self._model = ""
        self._cost = 0.0
        self._message_count = 0
        self._streaming_indicator: str | None = None
        self._group_mode: str | None = None
        self._typing_indicator: str | None = None
        self._connection_status: str | None = None
        self._encrypted: bool = False
        self._workspace_name: str | None = None
        self._permission_mode: str | None = None
        self._context_tokens: int = 0
        self._context_max: int = 200_000

    def update_info(
        self,
        session_name: str | None = None,
        model: str | None = None,
        cost: float | None = None,
        message_count: int | None = None,
        group_mode: str | None = None,
        clear_group_mode: bool = False,
        workspace_name: str | None = ...,
        permission_mode: str | None = ...,
    ) -> None:
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
        if workspace_name is not ...:
            self._workspace_name = workspace_name
        if permission_mode is not ...:
            self._permission_mode = permission_mode
        self._refresh_display()

    def set_streaming(
        self,
        tokens: int | None = None,
        elapsed: float | None = None,
        active: bool = True,
    ) -> None:
        if not active:
            self._streaming_indicator = None
        elif tokens is not None and elapsed is not None and elapsed > 0 and tokens > 0:
            rate = tokens / elapsed
            self._streaming_indicator = f"{rate:.0f} tok/s"
        else:
            self._streaming_indicator = "thinking..."
        self._refresh_display()

    def set_typing_indicator(self, names: list[str]) -> None:
        if not names:
            self._typing_indicator = None
        elif len(names) == 1:
            self._typing_indicator = f"{names[0]} is typing..."
        else:
            self._typing_indicator = f"{', '.join(names)} are typing..."
        self._refresh_display()

    def set_connection_status(self, status: str | None) -> None:
        self._connection_status = status
        self._refresh_display()

    def set_encrypted(self, encrypted: bool) -> None:
        self._encrypted = encrypted
        self._refresh_display()

    def set_context(self, tokens: int, max_tokens: int) -> None:
        """Update the context usage gauge."""
        self._context_tokens = tokens
        self._context_max = max_tokens
        self._refresh_display()

    def _refresh_display(self) -> None:
        parts: list[str] = []

        # Left: session name
        parts.append(self._session_name)

        # Workspace (only if set)
        if self._workspace_name:
            parts.append(f"[{self._workspace_name}]")

        # Transient states take priority
        if self._connection_status:
            parts.append(self._connection_status)
        elif self._typing_indicator:
            parts.append(self._typing_indicator)
        elif self._streaming_indicator:
            parts.append(self._streaming_indicator)
        else:
            # Context gauge (only when not streaming/typing)
            ctx = _context_bar(self._context_tokens, self._context_max)
            if ctx:
                parts.append(ctx)
            # Model
            if self._model:
                parts.append(self._model)

        # Conditional badges (only when non-default)
        if self._encrypted:
            parts.append("Encrypted")

        _mode_labels = {
            "humans_only": "Humans Only",
            "claude_assists": "Claude Assists",
            "full_auto": "Full Auto",
            "claude_to_claude": "C2C",
            "own": "Claude Assists", "mentions": "Humans Only",
            "all": "Full Auto", "off": "Humans Only",
        }
        if self._group_mode is not None:
            parts.append(_mode_labels.get(self._group_mode, self._group_mode))

        # Only show bypass permissions — other modes are normal operation
        if self._permission_mode == "bypassPermissions":
            parts.append("!! BYPASS !!")

        # Cost (always, right side)
        if self._cost > 0:
            parts.append(f"${self._cost:.4f}")

        self.update(" | ".join(parts))
