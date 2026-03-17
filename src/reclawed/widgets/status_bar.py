"""Minimal status bar — styled after Claude Code CLI status line."""

from __future__ import annotations

import subprocess
from textual.widgets import Static

# Model display name mapping
_MODEL_SHORT: dict[str, str] = {
    "claude-opus-4-6": "Opus 4.6",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-haiku-4-5": "Haiku 4.5",
    "claude-sonnet-4-5": "Sonnet 4.5",
    "claude-opus-4-5-20250918": "Opus 4.5",
}


def _short_model(model: str) -> str:
    if not model:
        return ""
    if model in _MODEL_SHORT:
        return _MODEL_SHORT[model]
    return model.replace("claude-", "").replace("-", " ").title()


def _format_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _context_gauge(tokens: int, max_tokens: int) -> str:
    """Compact context gauge: [###..] 16%"""
    if max_tokens <= 0 or tokens <= 0:
        return ""
    pct = min(tokens / max_tokens, 1.0)
    bar_width = 5
    filled = round(pct * bar_width)
    empty = bar_width - filled
    bar = "#" * filled + "." * empty
    return f"[{bar}] {pct:.0%}"


def _git_info(cwd: str | None) -> str | None:
    """Get git branch + status counts: master +2 ~1 ?3"""
    if not cwd:
        return None
    try:
        # Get branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd, capture_output=True, text=True, timeout=2,
        )
        if branch_result.returncode != 0:
            return None
        branch = branch_result.stdout.strip()
        if not branch:
            return None
        # Truncate long branch names
        if len(branch) > 20:
            branch = branch[:17] + "..."

        # Get status counts
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd, capture_output=True, text=True, timeout=2,
        )
        parts = [branch]
        if status_result.returncode == 0 and status_result.stdout.strip():
            lines = status_result.stdout.strip().splitlines()
            staged = sum(1 for l in lines if len(l) >= 2 and l[0] in "MADRC")
            modified = sum(1 for l in lines if len(l) >= 2 and l[1] == "M")
            untracked = sum(1 for l in lines if l.startswith("??"))
            if staged:
                parts.append(f"+{staged}")
            if modified:
                parts.append(f"~{modified}")
            if untracked:
                parts.append(f"?{untracked}")
            if not staged and not modified and not untracked:
                parts.append("+0")
        else:
            parts.append("+0")

        return " ".join(parts)
    except Exception:
        return None


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
        self._workspace_cwd: str | None = None
        self._permission_mode: str | None = None
        self._context_tokens: int = 0
        self._context_max: int = 200_000
        self._git_info_str: str | None = None

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
        cwd: str | None = ...,
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
        if cwd is not ...:
            self._workspace_cwd = cwd
            self._git_info_str = _git_info(cwd)
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
        self._context_tokens = tokens
        self._context_max = max_tokens
        self._refresh_display()

    def refresh_git(self) -> None:
        self._git_info_str = _git_info(self._workspace_cwd)
        self._refresh_display()

    def _refresh_display(self) -> None:
        parts: list[str] = []

        # Workspace
        if self._workspace_name:
            parts.append(self._workspace_name)

        # Git info: branch +staged ~modified ?untracked
        if getattr(self, "_git_info_str", None):
            parts.append(self._git_info_str)

        # Transient states
        if self._connection_status:
            parts.append(self._connection_status)
        elif self._typing_indicator:
            parts.append(self._typing_indicator)
        elif self._streaming_indicator:
            parts.append(self._streaming_indicator)

        # Model (short name)
        if self._model:
            parts.append(_short_model(self._model))

        # Context gauge
        ctx = _context_gauge(self._context_tokens, self._context_max)
        if ctx:
            parts.append(ctx)

        # Token count
        if self._context_tokens > 0:
            parts.append(_format_tokens(self._context_tokens))

        # Conditional badges
        if self._encrypted:
            parts.append("ENC")

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

        if self._permission_mode == "bypassPermissions":
            parts.append("BYPASS")

        # Cost
        if self._cost > 0:
            parts.append(f"${self._cost:.2f}")

        self.update(" | ".join(parts))
