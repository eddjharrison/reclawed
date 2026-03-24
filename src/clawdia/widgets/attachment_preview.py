"""Attachment preview strip shown above compose area when images are queued."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Click
from textual.message import Message as TMessage
from textual.widgets import Label, Static

from clawdia.utils import format_file_size


class _ChipRemoveButton(Label):
    """Tiny [x] button inside an attachment chip."""

    DEFAULT_CSS = """
    _ChipRemoveButton {
        width: auto;
        height: 1;
        margin: 0 0 0 0;
        color: $text-muted;
    }
    _ChipRemoveButton:hover {
        color: $error;
        text-style: bold;
    }
    """

    def __init__(self, file_path: str, **kwargs) -> None:
        super().__init__(" [x]", **kwargs)
        self._file_path = file_path

    def on_click(self, event: Click) -> None:
        event.stop()
        self.post_message(AttachmentChip.Removed(self._file_path))


class _ChipLabel(Label):
    """Clickable label inside an attachment chip — opens preview."""

    DEFAULT_CSS = """
    _ChipLabel {
        width: auto;
        height: 1;
    }
    _ChipLabel:hover {
        text-style: underline;
    }
    """

    def __init__(self, text: str, file_path: str, **kwargs) -> None:
        super().__init__(text, **kwargs)
        self._file_path = file_path

    def on_click(self, event: Click) -> None:
        event.stop()
        self.post_message(AttachmentChip.PreviewRequested(self._file_path))


class AttachmentChip(Horizontal):
    """Single attachment chip — click label to preview, click [x] to remove."""

    DEFAULT_CSS = """
    AttachmentChip {
        width: auto;
        height: 1;
        margin: 0 1 0 0;
        background: $primary 20%;
        color: $text;
    }
    """

    class Removed(TMessage):
        """Posted when the user removes an attachment."""
        def __init__(self, path: str) -> None:
            super().__init__()
            self.path = path

    class PreviewRequested(TMessage):
        """Posted when the user clicks to preview an attachment."""
        def __init__(self, path: str) -> None:
            super().__init__()
            self.path = path

    def __init__(self, file_path: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._file_path = file_path
        p = Path(file_path)
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        self._display_text = f" 📁 {p.name} ({format_file_size(size)})"

    def compose(self) -> ComposeResult:
        yield _ChipLabel(self._display_text, self._file_path)
        yield _ChipRemoveButton(self._file_path)


class AttachmentPreview(Horizontal):
    """Horizontal strip of attachment chips shown above compose area."""

    DEFAULT_CSS = """
    AttachmentPreview {
        width: 100%;
        height: auto;
        max-height: 3;
        padding: 0 1;
        display: none;
    }
    AttachmentPreview.has-attachments {
        display: block;
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
