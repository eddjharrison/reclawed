"""Attachment preview strip shown above compose area when images are queued."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message as TMessage
from textual.widgets import Button, Label, Static

from reclawed.utils import format_file_size, get_image_mime


class AttachmentChip(Horizontal):
    """Single attachment chip with filename and remove button."""

    DEFAULT_CSS = """
    AttachmentChip {
        width: auto;
        height: 3;
        padding: 0 1;
        margin: 0 1 0 0;
        background: $primary 20%;
        border: tall $primary;
    }
    AttachmentChip .chip-icon {
        width: 3;
        color: $accent;
    }
    AttachmentChip .chip-label {
        width: auto;
        max-width: 30;
        color: $text;
    }
    AttachmentChip .chip-size {
        width: auto;
        color: $text-muted;
        margin-left: 1;
    }
    AttachmentChip .chip-remove {
        width: 3;
        min-width: 3;
        margin-left: 1;
        color: $error;
        background: transparent;
        border: none;
    }
    """

    class Removed(TMessage):
        """Posted when the user removes an attachment."""
        def __init__(self, path: str) -> None:
            super().__init__()
            self.path = path

    def __init__(self, file_path: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._file_path = file_path
        p = Path(file_path)
        self._filename = p.name
        try:
            self._size = p.stat().st_size
        except OSError:
            self._size = 0

    def compose(self) -> ComposeResult:
        yield Label("📁", classes="chip-icon")
        yield Label(self._filename, classes="chip-label")
        yield Label(f"({format_file_size(self._size)})", classes="chip-size")
        yield Button("x", classes="chip-remove", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.post_message(self.Removed(self._file_path))


class AttachmentPreview(Horizontal):
    """Horizontal strip of attachment chips shown above compose area."""

    DEFAULT_CSS = """
    AttachmentPreview {
        width: 100%;
        height: auto;
        max-height: 5;
        padding: 0 1;
        display: none;
    }
    AttachmentPreview.has-attachments {
        display: block;
    }
    AttachmentPreview .attach-label {
        width: auto;
        color: $text-muted;
        margin-right: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._paths: list[str] = []

    @property
    def paths(self) -> list[str]:
        return list(self._paths)

    def add_attachment(self, path: str) -> None:
        """Add an attachment to the preview strip."""
        if path in self._paths:
            return
        self._paths.append(path)
        chip = AttachmentChip(path, id=f"chip-{len(self._paths)}")
        self.mount(chip)
        self.add_class("has-attachments")

    def remove_attachment(self, path: str) -> None:
        """Remove an attachment from the preview strip."""
        if path not in self._paths:
            return
        idx = self._paths.index(path)
        self._paths.remove(path)
        try:
            chip = self.query_one(f"#chip-{idx + 1}", AttachmentChip)
            chip.remove()
        except Exception:
            pass
        if not self._paths:
            self.remove_class("has-attachments")

    def clear(self) -> None:
        """Remove all attachments."""
        self._paths.clear()
        for chip in self.query(AttachmentChip):
            chip.remove()
        self.remove_class("has-attachments")

    def on_attachment_chip_removed(self, event: AttachmentChip.Removed) -> None:
        """Handle chip removal."""
        event.stop()
        self.remove_attachment(event.path)
