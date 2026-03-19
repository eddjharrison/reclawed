"""Memory browser — view and edit Claude's per-project memory files.

Memory files live in ``~/.claude/projects/<project-slug>/memory/``.
The project slug is derived by replacing every ``/`` in the CWD with ``-``.

Keybindings
-----------
``Ctrl+M``  Open from ChatScreen (wired in chat.py)
``Enter``   Open selected file in DocumentScreen (full-screen edit/view)
``n``       Create a new memory file
``d``       Delete selected file (with confirmation)
``Esc``     Close
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from reclawed.screens.document import DocumentScreen


def _memory_dir_for_cwd(cwd: str | None) -> Path | None:
    """Return the Claude memory directory for the given working directory.

    Claude stores per-project memories at::

        ~/.claude/projects/<slug>/memory/

    where ``<slug>`` is the CWD path with every ``/`` replaced by ``-``.

    Returns ``None`` if *cwd* is not provided.
    """
    if not cwd:
        return None
    slug = cwd.replace("/", "-").replace("\\", "-")
    return Path.home() / ".claude" / "projects" / slug / "memory"


def _human_size(path: Path) -> str:
    """Return a human-readable file size string."""
    try:
        size = path.stat().st_size
    except OSError:
        return "?"
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size}{unit}"
        size //= 1024
    return f"{size}MB"


class MemoryScreen(ModalScreen[bool]):
    """Two-panel memory file browser.

    Left panel: list of ``.md`` files in the project's memory directory.
    Right panel: live preview of the selected file's content.

    Press ``Enter`` to open the selected file in ``DocumentScreen`` for
    full editing.  Press ``n`` to create a new memory file, ``d`` to
    delete the selected one.
    """

    DEFAULT_CSS = """
    MemoryScreen {
        align: center middle;
    }

    MemoryScreen > #memory-outer {
        width: 90%;
        height: 85%;
        background: $surface;
        border: tall $primary;
        layout: vertical;
    }

    /* ── title bar ─────────────────────────────────────────────────── */
    MemoryScreen #memory-title {
        width: 100%;
        height: 1;
        background: $primary;
        color: $background;
        text-style: bold;
        padding: 0 2;
    }

    /* ── two-panel body ─────────────────────────────────────────────── */
    MemoryScreen #memory-body {
        width: 100%;
        height: 1fr;
        layout: horizontal;
    }

    /* ── left: file list ─────────────────────────────────────────────── */
    MemoryScreen #file-panel {
        width: 30;
        height: 100%;
        border-right: solid $primary 30%;
        layout: vertical;
    }
    MemoryScreen #file-panel-header {
        width: 100%;
        height: 1;
        background: $primary 20%;
        color: $text-muted;
        padding: 0 1;
        text-style: bold;
    }
    MemoryScreen ListView {
        width: 100%;
        height: 1fr;
        background: transparent;
    }
    MemoryScreen ListItem {
        width: 100%;
        padding: 0 1;
    }
    MemoryScreen .file-name {
        width: 100%;
    }
    MemoryScreen .empty-hint {
        color: $text-muted;
        padding: 1 2;
        width: 100%;
    }

    /* ── right: preview ─────────────────────────────────────────────── */
    MemoryScreen #preview-panel {
        width: 1fr;
        height: 100%;
        layout: vertical;
    }
    MemoryScreen #preview-panel-header {
        width: 100%;
        height: 1;
        background: $primary 20%;
        color: $text-muted;
        padding: 0 1;
        text-style: bold;
    }
    MemoryScreen #preview-content {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        color: $text;
        overflow-y: auto;
    }

    /* ── toolbar ─────────────────────────────────────────────────────── */
    MemoryScreen #memory-toolbar {
        width: 100%;
        height: 3;
        background: $primary 15%;
        layout: horizontal;
        padding: 0 1;
        align: left middle;
    }
    MemoryScreen #memory-toolbar Button {
        margin: 0 1 0 0;
        min-width: 10;
    }
    MemoryScreen #memory-status {
        width: 1fr;
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }

    /* ── new-file input row ───────────────────────────────────────────── */
    MemoryScreen #new-file-row {
        width: 100%;
        height: 3;
        background: $primary 10%;
        layout: horizontal;
        padding: 0 1;
        align: left middle;
        display: none;
    }
    MemoryScreen #new-file-row.visible {
        display: block;
    }
    MemoryScreen #new-file-input {
        width: 1fr;
    }
    MemoryScreen #new-file-row Label {
        width: auto;
        margin: 0 1 0 0;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("enter", "open_file", "Open", show=True),
        Binding("n", "new_file", "New", show=True),
        Binding("d", "delete_file", "Delete", show=True),
    ]

    def __init__(self, cwd: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cwd = cwd
        self._memory_dir: Path | None = _memory_dir_for_cwd(cwd)
        self._files: list[Path] = []
        self._selected_path: Path | None = None

    # ── compose ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        dir_label = str(self._memory_dir) if self._memory_dir else "No project selected"

        with Vertical(id="memory-outer"):
            yield Label(f" 🧠 Memory Files  —  {dir_label}", id="memory-title")

            with Horizontal(id="memory-body"):
                # ── left panel ──────────────────────────────────────────
                with Vertical(id="file-panel"):
                    yield Label("Files", id="file-panel-header")
                    yield ListView(id="file-list")

                # ── right panel ─────────────────────────────────────────
                with Vertical(id="preview-panel"):
                    yield Label("Preview", id="preview-panel-header")
                    yield Static("", id="preview-content")

            # ── toolbar ─────────────────────────────────────────────────
            with Horizontal(id="memory-toolbar"):
                yield Button("Open (Enter)", id="btn-open", variant="primary")
                yield Button("New (n)", id="btn-new", variant="default")
                yield Button("Delete (d)", id="btn-delete", variant="error")
                yield Label("", id="memory-status")

            # ── new file input (hidden until 'n' pressed) ────────────────
            with Horizontal(id="new-file-row"):
                yield Label("New filename:")
                yield Input(
                    placeholder="notes.md — press Enter to create, Esc to cancel",
                    id="new-file-input",
                )

    def on_mount(self) -> None:
        self._refresh_file_list()

    # ── file list ─────────────────────────────────────────────────────────

    def _refresh_file_list(self) -> None:
        """Scan memory directory and rebuild the ListView."""
        lv = self.query_one("#file-list", ListView)
        lv.clear()
        self._files = []

        if not self._memory_dir or not self._memory_dir.exists():
            lv.mount(ListItem(Label("(no memory files yet)", classes="empty-hint")))
            self._update_preview(None)
            return

        files = sorted(
            [f for f in self._memory_dir.iterdir() if f.suffix in {".md", ".txt", ".json", ".toml"}],
            key=lambda f: f.name,
        )
        self._files = files

        if not files:
            lv.mount(ListItem(Label("(no memory files yet)", classes="empty-hint")))
            self._update_preview(None)
            return

        for f in files:
            size = _human_size(f)
            lv.mount(ListItem(Label(f" {f.name}  [{size}]", classes="file-name")))

        # Select first file
        self.query_one("#file-list", ListView).index = 0
        if files:
            self._selected_path = files[0]
            self._update_preview(files[0])

    def _update_preview(self, path: Path | None) -> None:
        """Show a truncated preview of the selected file."""
        preview = self.query_one("#preview-content", Static)
        header = self.query_one("#preview-panel-header", Label)
        status = self.query_one("#memory-status", Label)

        if path is None:
            preview.update("(nothing selected)")
            header.update("Preview")
            status.update("")
            return

        header.update(f"Preview  —  {path.name}")
        try:
            text = path.read_text(encoding="utf-8")
            # Show first 60 lines as preview
            lines = text.splitlines()[:60]
            preview.update("\n".join(lines))
            size = _human_size(path)
            total_lines = text.count("\n") + 1
            status.update(f"{path.name}  │  {total_lines} lines  │  {size}")
        except OSError as exc:
            preview.update(f"[Error: {exc}]")
            status.update("")

    # ── actions ───────────────────────────────────────────────────────────

    def action_close(self) -> None:
        self.dismiss(False)

    async def action_open_file(self) -> None:
        """Open the selected file in DocumentScreen for full-screen editing."""
        if self._selected_path is None:
            self.notify("No file selected", severity="warning", timeout=2)
            return
        saved = await self.app.push_screen_wait(
            DocumentScreen(
                path=self._selected_path,
                mode="edit",
                title=self._selected_path.name,
            )
        )
        if saved:
            self._update_preview(self._selected_path)

    def action_new_file(self) -> None:
        """Show the inline new-file input row."""
        if self._memory_dir is None:
            self.notify("No project memory directory available", severity="warning", timeout=3)
            return
        row = self.query_one("#new-file-row")
        row.add_class("visible")
        inp = self.query_one("#new-file-input", Input)
        inp.clear()
        inp.focus()

    async def _create_new_file(self, name: str) -> None:
        """Create the file and open it for editing."""
        if not name or self._memory_dir is None:
            return

        p = Path(name)
        if not p.suffix:
            p = p.with_suffix(".md")

        new_path = self._memory_dir / p.name
        if new_path.exists():
            self.notify(f"{p.name} already exists", severity="warning", timeout=3)
            return

        try:
            self._memory_dir.mkdir(parents=True, exist_ok=True)
            new_path.write_text("", encoding="utf-8")
        except OSError as exc:
            self.notify(f"Failed to create file: {exc}", severity="error", timeout=5)
            return

        # Hide input row
        self.query_one("#new-file-row").remove_class("visible")

        self._refresh_file_list()
        # Navigate to new file
        try:
            idx = next(i for i, f in enumerate(self._files) if f == new_path)
            self.query_one("#file-list", ListView).index = idx
            self._selected_path = new_path
            self._update_preview(new_path)
        except StopIteration:
            pass

        # Open it immediately for editing
        await self.action_open_file()

    async def action_delete_file(self) -> None:
        """Delete the selected memory file after confirmation."""
        if self._selected_path is None:
            self.notify("No file selected", severity="warning", timeout=2)
            return

        from reclawed.widgets.confirm_screen import ConfirmScreen  # local import
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(
                "Delete Memory File",
                f"Delete '{self._selected_path.name}'? This cannot be undone.",
            )
        )
        if not confirmed:
            return

        try:
            self._selected_path.unlink()
        except OSError as exc:
            self.notify(f"Delete failed: {exc}", severity="error", timeout=5)
            return

        self.notify(f"Deleted {self._selected_path.name}", severity="information", timeout=2)
        self._selected_path = None
        self._refresh_file_list()

    # ── event handlers ────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Create the new file when Enter is pressed in the name input."""
        if event.input.id != "new-file-input":
            return
        name = event.value.strip()
        self.query_one("#new-file-row").remove_class("visible")
        if name:
            self.run_worker(self._create_new_file(name), exclusive=False)

    def on_key(self, event) -> None:  # type: ignore[override]
        """Close the new-file input row on Escape."""
        row = self.query_one("#new-file-row")
        if event.key == "escape" and "visible" in row.classes:
            row.remove_class("visible")
            self.query_one("#file-list", ListView).focus()
            event.stop()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Update preview when a file is selected in the list."""
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self._files):
            self._selected_path = self._files[idx]
            self._update_preview(self._selected_path)
        else:
            self._selected_path = None
            self._update_preview(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-open":
            self.run_action("open_file")
        elif event.button.id == "btn-new":
            self.run_action("new_file")
        elif event.button.id == "btn-delete":
            self.run_action("delete_file")
