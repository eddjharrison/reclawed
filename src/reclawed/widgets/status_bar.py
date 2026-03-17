"""Minimal status bar — styled after Claude Code CLI status line."""

from __future__ import annotations

from textual.widgets import Static

# Model display name mapping — short codes like Claude Code uses
_MODEL_SHORT: dict[str, str] = {
    "claude-opus-4-6": "Opus 4.6",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-haiku-4-5": "Haiku 4.5",
    "claude-sonnet-4-5": "Sonnet 4.5",
    "claude-opus-4-5-20250918": "Opus 4.5",
}


def _short_model(model: str) -> str:
    """Return a short display name for the model."""
    if not model:
        return ""
    if model in _MODEL_SHORT:
        return _MODEL_SHORT[model]
    # Fallback: strip "claude-" prefix and clean up
    short = model.replace("claude-", "").replace("-", " ").title()
    return short


def _battery_gauge(tokens: int, max_tokens: int) -> str:
    """Render a battery-style context gauge: 🔋[██░░░] 16%"""
    if max_tokens <= 0 or tokens <= 0:
        return ""
    pct = min(tokens / max_tokens, 1.0)
    bar_width = 5
    filled = round(pct * bar_width)
    empty = bar_width - filled
    bar = "\u2588" * filled + "\u2591" * empty
    return f"[{bar}] {pct:.0%}"


class StatusBar(Static):
    """Bottom status bar — clean, minimal, context-aware."""

    DEFAULT_CSS = """
    StatusBar {
        width: 100%;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
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
        left_parts: list[str] = []
        right_parts: list[str] = []

        # Left side: workspace + context gauge
        if self._workspace_name:
            left_parts.append(f"\U0001f4c1 {self._workspace_name}")

        # Context gauge (battery style)
        ctx = _battery_gauge(self._context_tokens, self._context_max)
        if ctx:
            left_parts.append(ctx)

        # Transient states
        if self._connection_status:
            left_parts.append(self._connection_status)
        elif self._typing_indicator:
            left_parts.append(self._typing_indicator)
        elif self._streaming_indicator:
            left_parts.append(self._streaming_indicator)

        # Right side: badges, model, tokens, cost
        if self._encrypted:
            right_parts.append("\U0001f512")

        _mode_labels = {
            "humans_only": "Humans Only",
            "claude_assists": "Claude Assists",
            "full_auto": "Full Auto",
            "claude_to_claude": "C2C",
            "own": "Claude Assists", "mentions": "Humans Only",
            "all": "Full Auto", "off": "Humans Only",
        }
        if self._group_mode is not None:
            right_parts.append(_mode_labels.get(self._group_mode, self._group_mode))

        if self._permission_mode == "bypassPermissions":
            right_parts.append("!! BYPASS !!")

        # Model (short name)
        if self._model:
            right_parts.append(_short_model(self._model))

        # Token count
        if self._context_tokens > 0:
            if self._context_tokens >= 1000:
                right_parts.append(f"{self._context_tokens / 1000:.1f}k")
            else:
                right_parts.append(str(self._context_tokens))

        # Cost
        if self._cost > 0:
            right_parts.append(f"${self._cost:.4f}")

        left = " | ".join(left_parts) if left_parts else ""
        right = "  ".join(right_parts) if right_parts else ""

        if left and right:
            # Pad middle to push right side to the edge
            self.update(f"{left}  {right}")
        elif left:
            self.update(left)
        elif right:
            self.update(right)
        else:
            self.update("")
