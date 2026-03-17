"""Modal screen for entering a file path to attach."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class FileInputScreen(ModalScreen[str | None]):
    """Modal that asks the user for a file path.

    Dismisses with the file path string if valid, ``None`` if cancelled.
    """

    DEFAULT_CSS = """
    FileInputScreen {
        align: center middle;
    }
    FileInputScreen > #file-dialog {
        width: 70;
        height: auto;
        max-height: 14;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    FileInputScreen #file-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    FileInputScreen #file-hint {
        width: 100%;
        color: $text-muted;
        margin-bottom: 1;
    }
    FileInputScreen #file-error {
        width: 100%;
        color: $error;
        margin-bottom: 1;
        display: none;
    }
    FileInputScreen #file-error.visible {
        display: block;
    }
    FileInputScreen Input {
        width: 100%;
        margin-bottom: 1;
    }
    FileInputScreen #file-buttons {
        width: 100%;
        height: 3;
        align: center middle;
    }
    FileInputScreen #file-buttons Button {
        margin: 0 1;
    }
    """

    SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}

    def compose(self) -> ComposeResult:
        with Static(id="file-dialog"):
            yield Label("Attach Image", id="file-title")
            yield Label(
                "Enter the path to an image file (png, jpg, gif, webp)",
                id="file-hint",
            )
            yield Label("", id="file-error")
            yield Input(placeholder="C:\\path\\to\\image.png or /path/to/image.png", id="file-path-input")
            with Static(id="file-buttons"):
                yield Button("Attach", id="btn-attach", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="default")

    def on_mount(self) -> None:
        self.query_one("#file-path-input", Input).focus()

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in the input field."""
        self._try_attach()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-attach":
            self._try_attach()
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def _try_attach(self) -> None:
        """Validate the path and dismiss if valid."""
        path_input = self.query_one("#file-path-input", Input)
        error_label = self.query_one("#file-error", Label)
        raw = path_input.value.strip().strip('"').strip("'")

        if not raw:
            error_label.update("Please enter a file path")
            error_label.add_class("visible")
            return

        p = Path(raw)
        if not p.exists():
            error_label.update(f"File not found: {p.name}")
            error_label.add_class("visible")
            return

        if not p.is_file():
            error_label.update("Not a file")
            error_label.add_class("visible")
            return

        ext = p.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            error_label.update(f"Unsupported format: {ext} (use png, jpg, gif, webp)")
            error_label.add_class("visible")
            return

        size = p.stat().st_size
        if size > 20 * 1024 * 1024:
            error_label.update(f"File too large ({size // (1024*1024)}MB) — max 20MB")
            error_label.add_class("visible")
            return

        self.dismiss(str(p.resolve()))
