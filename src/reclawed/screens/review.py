"""Full-featured code review screen for unified diffs."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, RichLog

from textual import work

from reclawed.git_utils import FileDiff, parse_unified_diff
from reclawed.review_engine import Annotation, FileReview, review_file, format_review_markdown


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
        Binding("r", "ai_review", "AI Review", show=False),
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
        self._file_reviews: dict[str, FileReview] = {}  # cached AI reviews
        self._reviewing = False  # True while AI review is in progress
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
            f"{key.format('r')} AI Review",
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

        # Render AI review annotations if available
        review = self._file_reviews.get(file_diff.path)
        if review and review.annotations:
            log.write(Text(""))
            log.write(Text("\u2500\u2500\u2500 AI Review \u2500\u2500\u2500", style="bold yellow"))
            if review.summary:
                log.write(Text(f"  {review.summary}", style="italic dim"))
                log.write(Text(""))
            for a in review.annotations:
                hunk_label = f"hunk {a.hunk_index + 1}" if a.hunk_index < len(file_diff.hunks) else ""
                log.write(Text(f"  {a.emoji} [{a.severity.upper()}] {hunk_label}: {a.comment}"))
                if a.suggestion:
                    log.write(Text(f"    \u2192 {a.suggestion}", style="dim"))
        elif review and review.summary:
            log.write(Text(""))
            log.write(Text(f"  \u2705 {review.summary}", style="bold green"))

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

    def action_ai_review(self) -> None:
        """Trigger Claude AI review of the current file."""
        if not self._files:
            return
        file_diff = self._files[self._current_file_idx]
        if file_diff.path in self._file_reviews:
            self.notify("Already reviewed — re-rendering", timeout=1)
            self._render_current_file()
            return
        if self._reviewing:
            self.notify("Review in progress…", timeout=1)
            return
        self._reviewing = True
        self.notify(f"Reviewing {file_diff.path}…", timeout=2)
        self._run_ai_review(file_diff)

    @work(exclusive=True, group="ai-review")
    async def _run_ai_review(self, file_diff: FileDiff) -> None:
        """Run AI review in a worker thread."""
        try:
            # Detect model from app config if available
            model = "sonnet"
            try:
                from reclawed.screens.chat import ChatScreen
                screen = self.app.screen
                if isinstance(screen, ReviewScreen):
                    # Walk up the screen stack to find ChatScreen
                    for s in self.app.screen_stack:
                        if isinstance(s, ChatScreen):
                            model = s.session.model or "sonnet"
                            break
            except Exception:
                pass

            review = await review_file(
                file_path=file_diff.path,
                diff_text=file_diff.raw,
                model=model,
            )
            self._file_reviews[file_diff.path] = review
            n_issues = len(review.annotations)
            self.notify(
                f"Review complete: {n_issues} annotation{'s' if n_issues != 1 else ''}" +
                (f" — {review.summary}" if review.summary else ""),
                timeout=3,
            )
            self._render_current_file()
        except Exception as exc:
            self.notify(f"Review failed: {exc}", severity="error", timeout=5)
        finally:
            self._reviewing = False

    def action_post_review(self) -> None:
        """Post review to GitHub PR."""
        if not self._pr_number:
            self.notify("No PR number — cannot post review", severity="warning", timeout=3)
            return

        reviews = list(self._file_reviews.values())
        if not reviews and not self._file_statuses:
            self.notify("Nothing to post — review some files first", severity="warning", timeout=3)
            return

        self._post_review_to_github(reviews)

    @work(exclusive=True, group="post-review")
    async def _post_review_to_github(self, reviews: list[FileReview]) -> None:
        """Post the review to GitHub in a worker thread."""
        from reclawed.git_utils import post_pr_review

        # Build markdown body
        body = format_review_markdown(reviews, title=self._title)

        # Append manual file statuses
        approved = [p for p, s in self._file_statuses.items() if s == "approved"]
        rejected = [p for p, s in self._file_statuses.items() if s == "rejected"]
        if approved:
            body += f"\n\n**Approved:** " + ", ".join(f"`{p}`" for p in approved)
        if rejected:
            body += f"\n\n**Changes requested:** " + ", ".join(f"`{p}`" for p in rejected)

        # Determine event type
        has_errors = any(r.has_issues for r in reviews)
        has_rejections = bool(rejected)
        event = "request-changes" if (has_errors or has_rejections) else "comment"

        try:
            await post_pr_review(self._pr_number, body, event=event, cwd=self._cwd)
            self.notify(f"Review posted to PR #{self._pr_number}", timeout=3)
        except RuntimeError as exc:
            self.notify(f"Failed to post: {exc}", severity="error", timeout=5)
