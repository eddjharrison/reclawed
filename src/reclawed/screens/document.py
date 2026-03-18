"""Reusable document viewer / editor / diff screen.

Three modes
-----------
``view``  — Read-only display with syntax highlighting and search.
``edit``  — Full in-place editing with Ctrl+S save-to-disk.
``diff``  — Coloured unified diff (green additions, red removals).
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Literal

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, RichLog, TextArea

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".md": "markdown",
    ".markdown": "markdown",
    ".css": "css",
    ".tcss": "css",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".rs": "rust",
    ".go": "go",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".diff": "diff",
    ".patch": "diff",
}

# Languages known to be supported by Textual's tree-sitter integration.
_TEXTUAL_LANGUAGES = {
    "python", "markdown", "css", "html", "json",
    "sql", "bash", "rust", "go", "yaml", "toml",
}

Mode = Literal["view", "edit", "diff"]

_MODE_ICON = {"view": "👁 VIEW", "edit": "✏️  EDIT", "diff": "± DIFF"}


def _detect_language(path: Path | None, syntax_override: str | None) -> str | None:
    """Return a Textual-compatible language string, or None for plain text."""
    lang = syntax_override or (
        _EXTENSION_TO_LANGUAGE.get(path.suffix.lower()) if path else None
    )
    if lang == "diff":
        return None  # diff is rendered by RichLog, not TextArea
    return lang if lang in _TEXTUAL_LANGUAGES else None


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------

class DocumentScreen(ModalScreen[bool]):
    """Reusable document viewer / editor / diff screen.

    Parameters
    ----------
    path:
        Path to read (and write back to in ``edit`` mode).
    content:
        Raw string to display when no file path is given.
    before / after:
        Two strings; a unified diff is generated automatically and the
        screen switches to ``diff`` mode regardless of *mode* argument.
    mode:
        ``"view"`` | ``"edit"`` | ``"diff"`` (default ``"view"``).
    title:
        Header title; defaults to the filename or ``"Document"``.
    syntax:
        Language override for TextArea syntax highlighting.

    Dismisses with ``True`` if the file was saved, ``False`` otherwise.
    """

    DEFAULT_CSS = """
    DocumentScreen {
        align: center middle;
    }

    DocumentScreen > #doc-outer {
        width: 92%;
        height: 88%;
        background: $surface;
        border: tall $primary;
        layout: vertical;
    }

    /* ── header bar ─────────────────────────────────────── */
    DocumentScreen #doc-header {
        width: 100%;
        height: 1;
        background: $primary;
        color: $background;
        text-style: bold;
        padding: 0 2;
    }

    /* ── search bar ─────────────────────────────────────── */
    DocumentScreen #search-bar {
        width: 100%;
        height: 3;
        display: none;
        background: $surface-darken-1;
        border-bottom: solid $primary 40%;
        padding: 0 1;
    }
    DocumentScreen #search-bar.visible {
        display: block;
    }

    /* ── main content ───────────────────────────────────── */
    DocumentScreen #doc-area {
        width: 100%;
        height: 1fr;
    }
    DocumentScreen TextArea {
        width: 100%;
        height: 100%;
        border: none;
    }
    DocumentScreen RichLog {
        width: 100%;
        height: 100%;
        padding: 0 1;
    }

    /* ── status bar ─────────────────────────────────────── */
    DocumentScreen #doc-status {
        width: 100%;
        height: 1;
        background: $primary 25%;
        color: $text-muted;
        padding: 0 2;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("e", "toggle_edit", "Edit", show=True),
        Binding("ctrl+s", "save", "Save", show=True),
        Binding("ctrl+f", "search", "Search", show=True),
        Binding("n", "next_hunk", "Next hunk", show=False),
        Binding("p", "prev_hunk", "Prev hunk", show=False),
    ]

    def __init__(
        self,
        path: "Path | str | None" = None,
        content: str | None = None,
        before: str | None = None,
        after: str | None = None,
        mode: Mode = "view",
        title: str | None = None,
        syntax: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)

        self._path = Path(path) if path else None
        self._mode: Mode = mode
        self._syntax = syntax
        self._dirty = False
        self._saved = False
        self._hunk_positions: list[int] = []
        self._current_hunk = -1

        # Title
        self._title = title or (self._path.name if self._path else "Document")

        # Content resolution
        if before is not None and after is not None:
            # Generate unified diff and force diff mode
            b_lines = before.splitlines(keepends=True)
            a_lines = after.splitlines(keepends=True)
            self._content = "".join(
                difflib.unified_diff(
                    b_lines, a_lines,
                    fromfile=f"a/{self._title}",
                    tofile=f"b/{self._title}",
                )
            )
            self._mode = "diff"
        elif content is not None:
            self._content = content
        elif self._path and self._path.exists():
            try:
                self._content = self._path.read_text(encoding="utf-8")
            except OSError as exc:
                self._content = f"[Error reading file: {exc}]"
        else:
            self._content = ""

        self._line_count = self._content.count("\n") + 1

    # ── compose ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        language = _detect_language(self._path, self._syntax)

        with Vertical(id="doc-outer"):
            yield Label(self._header_text(), id="doc-header")

            yield Input(
                placeholder="Search… (Enter to jump, Esc to close)",
                id="search-bar",
            )

            with Vertical(id="doc-area"):
                if self._mode == "diff":
                    yield RichLog(
                        id="doc-richlog",
                        highlight=False,
                        markup=False,
                        wrap=False,
                    )
                else:
                    yield TextArea(
                        self._content,
                        language=language,
                        show_line_numbers=True,
                        read_only=(self._mode == "view"),
                        id="doc-textarea",
                        tab_behavior="indent",
                    )

            yield Label(self._status_text(), id="doc-status")

    def on_mount(self) -> None:
        if self._mode == "diff":
            self._render_diff()
        else:
            self.query_one("#doc-textarea", TextArea).focus()

    # ── diff rendering ──────────────────────────────────────────────────────

    def _render_diff(self) -> None:
        """Write coloured diff lines to RichLog and record hunk positions."""
        log = self.query_one("#doc-richlog", RichLog)
        self._hunk_positions = []
        for i, line in enumerate(self._content.splitlines()):
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

    # ── status / header helpers ─────────────────────────────────────────────

    def _header_text(self) -> str:
        icon = _MODE_ICON[self._mode]
        return f" {icon}  {self._title}"

    def _status_text(self) -> str:
        parts = [self._title, f"{self._line_count} lines", self._mode.upper()]
        if self._dirty:
            parts.append("● MODIFIED")
        return "  │  ".join(parts)

    def _refresh_header(self) -> None:
        try:
            self.query_one("#doc-header", Label).update(self._header_text())
        except Exception:
            pass

    def _refresh_status(self) -> None:
        try:
            self.query_one("#doc-status", Label).update(self._status_text())
        except Exception:
            pass

    # ── actions ────────────────────────────────────────────────────────────

    async def action_close(self) -> None:
        """Close the screen, optionally hiding the search bar first."""
        # If search bar is open, close it instead of the whole screen.
        try:
            bar = self.query_one("#search-bar", Input)
            if "visible" in bar.classes:
                bar.remove_class("visible")
                try:
                    self.query_one("#doc-textarea", TextArea).focus()
                except Exception:
                    pass
                return
        except Exception:
            pass

        # Warn before closing with unsaved changes.
        if self._dirty:
            from reclawed.widgets.confirm_screen import ConfirmScreen  # local import avoids cycle
            confirmed = await self.app.push_screen_wait(
                ConfirmScreen(
                    "Unsaved Changes",
                    "You have unsaved changes. Close anyway?",
                )
            )
            if not confirmed:
                return

        self.dismiss(self._saved)

    def action_toggle_edit(self) -> None:
        """Toggle view ↔ edit mode (unavailable in diff mode)."""
        if self._mode == "diff":
            self.notify("Edit not available in diff mode", severity="warning", timeout=2)
            return

        if self._mode == "view":
            self._mode = "edit"
            try:
                ta = self.query_one("#doc-textarea", TextArea)
                ta.read_only = False
                ta.focus()
            except Exception:
                pass
        else:
            self._mode = "view"
            try:
                ta = self.query_one("#doc-textarea", TextArea)
                ta.read_only = True
            except Exception:
                pass

        self._refresh_header()
        self._refresh_status()

    def action_save(self) -> None:
        """Write current content to disk (edit mode only)."""
        if self._mode != "edit":
            return
        if self._path is None:
            self.notify("No file path — cannot save", severity="warning", timeout=3)
            return
        try:
            content = self.query_one("#doc-textarea", TextArea).text
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(content, encoding="utf-8")
            self._content = content
            self._line_count = content.count("\n") + 1
            self._dirty = False
            self._saved = True
            self.notify(f"Saved {self._path.name}", severity="information", timeout=2)
            self._refresh_status()
        except OSError as exc:
            self.notify(f"Save failed: {exc}", severity="error", timeout=5)

    def action_search(self) -> None:
        """Toggle the search bar."""
        try:
            bar = self.query_one("#search-bar", Input)
        except Exception:
            return
        if "visible" in bar.classes:
            bar.remove_class("visible")
            try:
                self.query_one("#doc-textarea", TextArea).focus()
            except Exception:
                pass
        else:
            bar.add_class("visible")
            bar.focus()
            bar.clear()

    def action_next_hunk(self) -> None:
        """Jump to the next @@ hunk (diff mode)."""
        if not self._hunk_positions:
            return
        self._current_hunk = (self._current_hunk + 1) % len(self._hunk_positions)
        self.notify(
            f"Hunk {self._current_hunk + 1}/{len(self._hunk_positions)}",
            timeout=1,
        )

    def action_prev_hunk(self) -> None:
        """Jump to the previous @@ hunk (diff mode)."""
        if not self._hunk_positions:
            return
        self._current_hunk = (self._current_hunk - 1) % len(self._hunk_positions)
        self.notify(
            f"Hunk {self._current_hunk + 1}/{len(self._hunk_positions)}",
            timeout=1,
        )

    # ── event handlers ─────────────────────────────────────────────────────

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._mode == "edit":
            self._dirty = True
            self._line_count = event.text_area.text.count("\n") + 1
            self._refresh_status()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Naive substring search — moves cursor to first match."""
        if event.input.id != "search-bar":
            return
        query = event.value.strip()
        if not query:
            return
        try:
            ta = self.query_one("#doc-textarea", TextArea)
        except Exception:
            return

        text = ta.text
        idx = text.lower().find(query.lower())
        if idx == -1:
            self.notify(f"'{query}' not found", severity="warning", timeout=2)
            return

        before = text[:idx]
        row = before.count("\n")
        col = idx - (before.rfind("\n") + 1)
        ta.move_cursor((row, col))
        ta.focus()
