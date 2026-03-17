"""Status bar — styled after Claude Code CLI status line with Rich markup."""

from __future__ import annotations

import subprocess
from textual.widgets import Static

_MODEL_SHORT: dict[str, str] = {
    "claude-opus-4-6": "Opus 4.6 (1M context)",
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
        return f"{n / 1000:.0f}"
    return str(n)


def _context_battery(tokens: int, max_tokens: int) -> str:
    """Rich-markup battery gauge: green/yellow/red based on usage."""
    if max_tokens <= 0 or tokens <= 0:
        return ""
    pct = min(tokens / max_tokens, 1.0)
    pct_int = round(pct * 100)
    bar_width = 10
    filled = round(pct * bar_width)
    empty = bar_width - filled

    if pct < 0.5:
        color = "green"
    elif pct < 0.8:
        color = "yellow"
    else:
        color = "red"

    filled_chars = "\u2588" * filled
    empty_chars = "\u2591" * empty
    return f"\U0001f50b [{color}]{filled_chars}{empty_chars}[/{color}] {pct_int}%"


def _git_info(cwd: str | None) -> tuple[str | None, str | None]:
    """Get git branch and status. Returns (branch, status_str)."""
    if not cwd:
        return None, None
    try:
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd, capture_output=True, text=True, timeout=2,
        )
        if branch_result.returncode != 0:
            return None, None
        branch = branch_result.stdout.strip()
        if not branch:
            return None, None
        if len(branch) > 20:
            branch = branch[:17] + "..."

        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd, capture_output=True, text=True, timeout=2,
        )
        status_parts = []
        if status_result.returncode == 0 and status_result.stdout.strip():
            lines = status_result.stdout.strip().splitlines()
            staged = sum(1 for l in lines if len(l) >= 2 and l[0] in "MADRC")
            modified = sum(1 for l in lines if len(l) >= 2 and l[1] == "M")
            untracked = sum(1 for l in lines if l.startswith("??"))
            if staged:
                status_parts.append(f"[green]+{staged}[/green]")
            if modified:
                status_parts.append(f"[yellow]~{modified}[/yellow]")
            if untracked:
                status_parts.append(f"[red]?{untracked}[/red]")
            if not status_parts:
                status_parts.append("[green]+0[/green]")
        else:
            status_parts.append("[green]+0[/green]")

        status_str = " ".join(status_parts)
        return branch, status_str
    except Exception:
        return None, None


class StatusBar(Static):
    """Bottom status bar with Rich markup for colors and icons."""

    DEFAULT_CSS = """
    StatusBar {
        width: 100%;
        height: 1;
        background: $surface-darken-1;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", markup=True, **kwargs)
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
        self._git_branch: str | None = None
        self._git_status: str | None = None

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
            self._git_branch, self._git_status = _git_info(cwd)
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
            self._streaming_indicator = f"[bold]{rate:.0f} tok/s[/bold]"
        else:
            self._streaming_indicator = "[dim]thinking...[/dim]"
        self._refresh_display()

    def set_typing_indicator(self, names: list[str]) -> None:
        if not names:
            self._typing_indicator = None
        elif len(names) == 1:
            self._typing_indicator = f"[italic]{names[0]} is typing...[/italic]"
        else:
            self._typing_indicator = f"[italic]{', '.join(names)} are typing...[/italic]"
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
        self._git_branch, self._git_status = _git_info(self._workspace_cwd)
        self._refresh_display()

    def _refresh_display(self) -> None:
        parts: list[str] = []

        # Model
        if self._model:
            parts.append(f"\u2699 [bold cyan]{_short_model(self._model)}[/bold cyan]")

        # Context battery gauge
        ctx = _context_battery(self._context_tokens, self._context_max)
        if ctx:
            parts.append(ctx)

        # Workspace
        if self._workspace_name:
            parts.append(f"\U0001f4c1 [bold yellow]{self._workspace_name}[/bold yellow]")

        # Git: branch + status + token count
        git_branch = getattr(self, "_git_branch", None)
        git_status = getattr(self, "_git_status", None)
        if git_branch:
            git_parts = [f"\U0001f500 [green]{git_branch}[/green]"]
            if git_status:
                git_parts.append(git_status)
            if self._context_tokens > 0:
                git_parts.append(_format_tokens(self._context_tokens))
            parts.append(" ".join(git_parts))
        elif self._context_tokens > 0:
            parts.append(_format_tokens(self._context_tokens))

        # Transient states
        if self._connection_status:
            parts.append(f"[bold red]{self._connection_status}[/bold red]")
        elif self._typing_indicator:
            parts.append(self._typing_indicator)
        elif self._streaming_indicator:
            parts.append(self._streaming_indicator)

        # Badges
        if self._encrypted:
            parts.append("\U0001f512 [green]ENC[/green]")

        _mode_labels = {
            "humans_only": "Humans Only",
            "claude_assists": "Claude Assists",
            "full_auto": "Full Auto",
            "claude_to_claude": "C2C",
            "own": "Claude Assists", "mentions": "Humans Only",
            "all": "Full Auto", "off": "Humans Only",
        }
        if self._group_mode is not None:
            parts.append(f"[magenta]{_mode_labels.get(self._group_mode, self._group_mode)}[/magenta]")

        if self._permission_mode == "bypassPermissions":
            parts.append("[bold red]>> bypass permissions on[/bold red]")

        # Cost
        if self._cost > 0:
            parts.append(f"${self._cost:.2f}")

        self.update(" [dim]|[/dim] ".join(parts))
