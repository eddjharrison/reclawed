"""Quick file opener modal screen with path autocomplete."""

from __future__ import annotations

import glob as _glob
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

_MAX_SUGGESTIONS = 10


class FileOpenScreen(ModalScreen[str | None]):
    """Quick file opener with path autocomplete.

    Pre-fills the input with the current workspace ``cwd``.  As the user
    types, up to 10 matching filesystem entries are shown below the input.
    Tab accepts the highlighted suggestion.

    Dismisses with the resolved path string on success, ``None`` on cancel.
    """

    DEFAULT_CSS = """
    FileOpenScreen {
        align: center middle;
    }

    FileOpenScreen > Vertical#fo-dialog {
        width: 80;
        height: auto;
        max-height: 22;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    FileOpenScreen #fo-title {
        width: 100%;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    FileOpenScreen #fo-hint {
        width: 100%;
        color: $text-muted;
        margin-bottom: 1;
    }

    FileOpenScreen #fo-error {
        width: 100%;
        color: $error;
        margin-bottom: 1;
        display: none;
    }

    FileOpenScreen #fo-error.visible {
        display: block;
    }

    FileOpenScreen Input {
        width: 100%;
        margin-bottom: 0;
    }

    FileOpenScreen #fo-suggestions {
        width: 100%;
        height: auto;
        max-height: 12;
        display: none;
        background: $surface-darken-1;
        border: solid $primary 40%;
    }

    FileOpenScreen #fo-suggestions.visible {
        display: block;
    }

    FileOpenScreen ListView {
        width: 100%;
        height: auto;
        max-height: 12;
        background: transparent;
    }

    FileOpenScreen ListItem {
        padding: 0 1;
        color: $text;
    }

    FileOpenScreen ListItem.--highlight {
        background: $primary 30%;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("tab", "autocomplete", "Autocomplete", show=False, priority=True),
        Binding("enter", "submit_path", "Open", show=False, priority=True),
    ]

    def __init__(self, cwd: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cwd = cwd or str(Path.home())
        # Normalise: ensure trailing slash so glob suggestions work naturally
        if not self._cwd.endswith("/"):
            self._cwd += "/"

    # ── compose ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="fo-dialog"):
            yield Label("Open File", id="fo-title")
            yield Label(
                "Enter a file path — Tab to autocomplete, Enter to open",
                id="fo-hint",
            )
            yield Label("", id="fo-error")
            yield Input(value=self._cwd, id="fo-path-input")
            with Vertical(id="fo-suggestions"):
                yield ListView(id="fo-list")

    def on_mount(self) -> None:
        inp = self.query_one("#fo-path-input", Input)
        inp.focus()
        # Move cursor to end
        inp.cursor_position = len(inp.value)

    # ── autocomplete ───────────────────────────────────────────────────────

    def _get_suggestions(self, text: str) -> list[str]:
        """Return up to _MAX_SUGGESTIONS paths matching *text*."""
        if not text:
            return []
        try:
            pattern = text + "*"
            matches = _glob.glob(pattern, recursive=False)
            # Sort: directories first, then files
            matches.sort(key=lambda p: (not Path(p).is_dir(), p.lower()))
            # Append trailing slash to directories for easy continued typing
            result = []
            for m in matches[:_MAX_SUGGESTIONS]:
                if Path(m).is_dir() and not m.endswith("/"):
                    result.append(m + "/")
                else:
                    result.append(m)
            return result
        except Exception:
            return []

    def _refresh_suggestions(self, text: str) -> None:
        """Update the suggestions list based on current input value."""
        suggestions = self._get_suggestions(text)
        lv = self.query_one("#fo-list", ListView)
        suggestion_box = self.query_one("#fo-suggestions", Vertical)

        # Rebuild list
        lv.clear()
        for path in suggestions:
            lv.append(ListItem(Label(path)))

        if suggestions:
            suggestion_box.add_class("visible")
        else:
            suggestion_box.remove_class("visible")

    # ── event handlers ──────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "fo-path-input":
            return
        # Clear any prior error
        error = self.query_one("#fo-error", Label)
        error.remove_class("visible")
        self._refresh_suggestions(event.value)

    def on_key(self, event: Key) -> None:
        inp = self.query_one("#fo-path-input", Input)
        lv = self.query_one("#fo-list", ListView)
        suggestion_box = self.query_one("#fo-suggestions", Vertical)
        has_suggestions = "visible" in suggestion_box.classes and len(lv.children) > 0

        if event.key == "down":
            # Only intercept to transfer focus from input → list.
            # Once the list has focus, let ListView handle navigation.
            if inp.has_focus and has_suggestions:
                event.stop()
                event.prevent_default()
                lv.focus()
                lv.index = 0
        elif event.key == "up":
            # Only intercept to transfer focus from list → input at top.
            # Otherwise let ListView handle navigation natively.
            if lv.has_focus and has_suggestions and lv.index == 0:
                event.stop()
                event.prevent_default()
                inp.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Accept a suggestion when user clicks or presses Enter on it."""
        self._accept_highlighted_item(event.item)

    def _accept_suggestion(self) -> None:
        """Accept the first (or currently highlighted) suggestion into the input."""
        lv = self.query_one("#fo-list", ListView)
        suggestion_box = self.query_one("#fo-suggestions", Vertical)
        if "visible" not in suggestion_box.classes:
            return

        # If list has focus, accept highlighted item; otherwise accept first
        if lv.has_focus and lv.highlighted_child is not None:
            self._accept_highlighted_item(lv.highlighted_child)
        else:
            # Accept the first suggestion
            children = list(lv.children)
            if children:
                self._accept_list_item(children[0])

    def _accept_highlighted_item(self, item: "ListItem") -> None:
        self._accept_list_item(item)

    def _accept_list_item(self, item: "ListItem") -> None:
        try:
            label = item.query_one(Label)
            path_str = str(label.content)
        except Exception:
            self.log.error("Failed to extract path from list item", exc_info=True)
            return
        inp = self.query_one("#fo-path-input", Input)
        inp.value = path_str
        inp.cursor_position = len(path_str)
        inp.focus()
        # Refresh suggestions for the newly-accepted path
        self._refresh_suggestions(path_str)

    def _try_open(self) -> None:
        """Validate the entered path and dismiss with it if valid."""
        inp = self.query_one("#fo-path-input", Input)
        error = self.query_one("#fo-error", Label)
        raw = inp.value.strip().rstrip("/")

        if not raw:
            error.update("Please enter a file path")
            error.add_class("visible")
            return

        p = Path(raw)
        if not p.exists():
            error.update(f"Path not found: {p}")
            error.add_class("visible")
            return

        if p.is_dir():
            error.update(f"That is a directory, not a file: {p.name}")
            error.add_class("visible")
            return

        self.dismiss(str(p.resolve()))

    # ── actions ────────────────────────────────────────────────────────────

    def action_autocomplete(self) -> None:
        """Accept the highlighted (or first) suggestion into the input."""
        self._accept_suggestion()

    def action_submit_path(self) -> None:
        """Handle Enter — open file if input focused, accept suggestion if list focused."""
        inp = self.query_one("#fo-path-input", Input)
        lv = self.query_one("#fo-list", ListView)
        if lv.has_focus and lv.highlighted_child is not None:
            # Accept the highlighted suggestion into the input
            self._accept_highlighted_item(lv.highlighted_child)
        else:
            # Input has focus (or nothing specific) — try to open the path
            self._try_open()

    def action_cancel(self) -> None:
        self.dismiss(None)
