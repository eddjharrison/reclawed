"""Full-featured code review screen for unified diffs."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, RichLog

from reclawed.git_utils import FileDiff, parse_unified_diff


class ReviewScreen(ModalScreen[dict | None]):
    """Full-screen modal for reviewing git diffs file by file."""

    DEFAULT_CSS = """
    ReviewScreen {
        align: center middle;
    }
    ReviewScreen > #review-outer {
        width: 92%;
        height: 90%;
        background: $surface;
        border: tall $primary;
        layout: vertical;
    }
    #review-header {
        width: 100%;
        height: 1;
        background: $primary;
        color: $background;
        text-style: bold;
        padding: 0 2;
    }
    #review-file-nav {
        width: 100%;
        height: 1;
        background: $primary 40%;
        color: $text;
        text-style: bold;
        padding: 0 2;
    }
    #review-diff {
        width: 100%;
        height: 1fr;
        padding: 0 1;
    }
    #review-annotations {
        width: 100%;
        height: auto;
        max-height: 8;
        display: none;
        background: $surface-darken-1;
        border-top: solid $accent 40%;
        padding: 1 2;
    }
    #review-annotations.visible {
        display: block;
    }
    #review-status {
        width: 100%;
        height: 1;
        background: $primary 25%;
        color: $text-muted;
        padding: 0 2;
    }
    #review-shortcuts {
        width: 100%;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("left", "prev_file", "Prev File", priority=True),
        Binding("right", "next_file", "Next File", priority=True),
        Binding("n", "next_hunk", "Next Hunk", show=False),
        Binding("p", "prev_hunk", "Prev Hunk", show=False),
        Binding("a", "approve_file", "Approve", show=False),
        Binding("x", "reject_file", "Reject", show=False),
        Binding("ctrl+p", "post_review", "Post Review", show=False, priority=True),
    ]

    def __init__(
        self,
        diff_text: str,
        title: str = "Code Review",
        pr_number: int | None = None,
        cwd: str = ".",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._diff_text = diff_text
        self._files: list[FileDiff] = parse_unified_diff(diff_text)
        self._current_file_idx = 0
        self._hunk_positions: list[int] = []
        self._current_hunk = -1
        self._file_statuses: dict[str, str] = {}  # path -> "approved" | "rejected" | "pending"
        self._annotations: dict[str, list[dict]] = {}  # path -> [{hunk_idx, comment, severity}]
        self._pr_number = pr_number
        self._cwd = cwd
        self._title = title

    # ── compose ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="review-outer"):
            yield Label(self._header_text(), id="review-header")
            yield Label(self._file_nav_text(), id="review-file-nav")
            yield RichLog(id="review-diff", highlight=False, markup=False, wrap=False)
            with Vertical(id="review-annotations"):
                yield Label("", id="review-annotations-content")
            yield Label(self._status_text(), id="review-status")
            yield Label(self._shortcuts_text(), id="review-shortcuts", markup=True)

    def on_mount(self) -> None:
        if self._files:
            self._render_current_file()
        else:
            log = self.query_one("#review-diff", RichLog)
            log.write(Text("No files in diff.", style="dim"))

    # ── header / status helpers ────────────────────────────────────────────

    def _header_text(self) -> str:
        n_files = len(self._files)
        total_add = sum(f.additions for f in self._files)
        total_del = sum(f.deletions for f in self._files)
        return f" \u2318 CODE REVIEW: {n_files} files (+{total_add} -{total_del}) \u2500\u2500 {self._title}"

    def _file_nav_text(self) -> str:
        if not self._files:
            return "  (no files)"
        f = self._files[self._current_file_idx]
        idx = self._current_file_idx + 1
        total = len(self._files)
        return f"  \u2190 {f.path} ({idx}/{total}) \u2192"

    def _status_text(self) -> str:
        if not self._files:
            return "  No files"
        f = self._files[self._current_file_idx]
        status = self._file_statuses.get(f.path, "pending")
        icon = {"approved": "\u2705", "rejected": "\u274c", "pending": "\u25cf"}[status]
        n_hunks = len(f.hunks)
        return f"  {f.path}  \u2502  +{f.additions}/-{f.deletions}  \u2502  {n_hunks} hunks  \u2502  {icon} {status.title()}"

    def _shortcuts_text(self) -> str:
        key = "[bold]{}[/bold]"
        hints = [
            f"{key.format('Esc')} Close",
            f"{key.format('\u2190/\u2192')} Files",
            f"{key.format('n/p')} Hunks",
            f"{key.format('a')} Approve",
            f"{key.format('x')} Reject",
        ]
        if self._pr_number:
            hints.append(f"{key.format('Ctrl+P')} Post Review")
        return "  ".join(hints)

    def _refresh_ui(self) -> None:
        try:
            self.query_one("#review-header", Label).update(self._header_text())
        except Exception:
            pass
        try:
            self.query_one("#review-file-nav", Label).update(self._file_nav_text())
        except Exception:
            pass
        try:
            self.query_one("#review-status", Label).update(self._status_text())
        except Exception:
            pass
        try:
            self.query_one("#review-shortcuts", Label).update(self._shortcuts_text())
        except Exception:
            pass

    # ── diff rendering ─────────────────────────────────────────────────────

    def _render_current_file(self) -> None:
        """Render the diff for the current file into the RichLog."""
        log = self.query_one("#review-diff", RichLog)
        log.clear()
        self._hunk_positions = []
        self._current_hunk = -1

        if not self._files:
            return

        file_diff = self._files[self._current_file_idx]

        for i, line in enumerate(file_diff.raw.splitlines()):
            text = Text(line, no_wrap=True)
            if line.startswith("@@"):
                text.stylize("bold cyan")
                self._hunk_positions.append(i)
            elif line.startswith("+") and not line.startswith("+++"):
                text.stylize("bold green")
            elif line.startswith("-") and not line.startswith("---"):
                text.stylize("bold red")
            elif line.startswith(("---", "+++")):
                text.stylize("dim")
            log.write(text)

        # Render inline annotations if any
        annots = self._annotations.get(file_diff.path, [])
        if annots:
            log.write(Text(""))
            log.write(Text("\u2500\u2500\u2500 Annotations \u2500\u2500\u2500", style="bold yellow"))
            severity_emoji = {"info": "\u2139\ufe0f", "warning": "\u26a0\ufe0f", "error": "\u274c"}
            for a in annots:
                emoji = severity_emoji.get(a.get("severity", "info"), "\U0001f4ac")
                log.write(Text(f"  {emoji} {a.get('comment', '')}", style="italic"))

        # Hide/show annotations panel
        annot_panel = self.query_one("#review-annotations")
        if annots:
            annot_panel.add_class("visible")
        else:
            annot_panel.remove_class("visible")

        self._refresh_ui()

    # ── actions ────────────────────────────────────────────────────────────

    def action_close(self) -> None:
        """Close and return summary of file statuses."""
        approved = [p for p, s in self._file_statuses.items() if s == "approved"]
        rejected = [p for p, s in self._file_statuses.items() if s == "rejected"]
        pending = [
            f.path for f in self._files
            if self._file_statuses.get(f.path, "pending") == "pending"
        ]
        self.dismiss({"approved": approved, "rejected": rejected, "pending": pending})

    def action_prev_file(self) -> None:
        if not self._files:
            return
        self._current_file_idx = (self._current_file_idx - 1) % len(self._files)
        self._render_current_file()

    def action_next_file(self) -> None:
        if not self._files:
            return
        self._current_file_idx = (self._current_file_idx + 1) % len(self._files)
        self._render_current_file()

    def action_next_hunk(self) -> None:
        if not self._hunk_positions:
            return
        self._current_hunk = (self._current_hunk + 1) % len(self._hunk_positions)
        self.notify(
            f"Hunk {self._current_hunk + 1}/{len(self._hunk_positions)}",
            timeout=1,
        )

    def action_prev_hunk(self) -> None:
        if not self._hunk_positions:
            return
        self._current_hunk = (self._current_hunk - 1) % len(self._hunk_positions)
        self.notify(
            f"Hunk {self._current_hunk + 1}/{len(self._hunk_positions)}",
            timeout=1,
        )

    def action_approve_file(self) -> None:
        if not self._files:
            return
        path = self._files[self._current_file_idx].path
        self._file_statuses[path] = "approved"
        self.notify(f"\u2705 Approved: {path}", timeout=2)
        self._refresh_ui()
        # Auto-advance to next file
        if self._current_file_idx < len(self._files) - 1:
            self._current_file_idx += 1
            self._render_current_file()

    def action_reject_file(self) -> None:
        if not self._files:
            return
        path = self._files[self._current_file_idx].path
        self._file_statuses[path] = "rejected"
        self.notify(f"\u274c Rejected: {path}", timeout=2)
        self._refresh_ui()

    def action_post_review(self) -> None:
        if not self._pr_number:
            self.notify("Post review coming soon", severity="information", timeout=3)
            return
        approved = [p for p, s in self._file_statuses.items() if s == "approved"]
        rejected = [p for p, s in self._file_statuses.items() if s == "rejected"]
        body_parts = []
        if approved:
            body_parts.append(f"**Approved ({len(approved)}):** " + ", ".join(f"`{p}`" for p in approved))
        if rejected:
            body_parts.append(f"**Rejected ({len(rejected)}):** " + ", ".join(f"`{p}`" for p in rejected))
        if body_parts:
            self.notify(f"Review ready to post for PR #{self._pr_number}", timeout=3)
        else:
            self.notify("No files reviewed yet", severity="warning", timeout=3)
