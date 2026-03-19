"""Sidebar resize handle — drag to resize the sidebar width."""

from __future__ import annotations

from textual.events import MouseDown, MouseMove, MouseUp
from textual.message import Message as TMessage
from textual.widgets import Static

_MIN_WIDTH = 20
_MAX_WIDTH = 80


class SidebarResizeHandle(Static):
    """A thin vertical strip between the sidebar and the chat panel.

    The user can click-and-drag it horizontally to adjust the sidebar width.
    Posts a :class:`SidebarResizeHandle.Resized` message while dragging and
    once more on release so the parent screen can persist the value.

    Layout note: the widget should be placed *between* the sidebar and the
    chat panel inside a ``Horizontal`` container and given ``id="resize-handle"``.
    """

    DEFAULT_CSS = """
    SidebarResizeHandle {
        width: 1;
        height: 100%;
        background: $surface;
    }
    SidebarResizeHandle:hover {
        background: $primary 40%;
    }
    SidebarResizeHandle.dragging {
        background: $primary 70%;
    }
    """

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    class Resized(TMessage):
        """Posted continuously while dragging and once on mouse-up.

        Attributes
        ----------
        new_width:
            Clamped integer column count for the sidebar.
        final:
            ``True`` only on the mouse-up event so the screen knows when to
            persist the value to config.
        """

        def __init__(self, new_width: int, *, final: bool = False) -> None:
            super().__init__()
            self.new_width = new_width
            self.final = final

    # ------------------------------------------------------------------
    # Internal state
    # ------------------------------------------------------------------

    # Instance-level flag — must not be a class variable so multiple
    # SidebarResizeHandle instances don't share state.
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._dragging: bool = False

    # ------------------------------------------------------------------
    # Mouse event handlers
    # ------------------------------------------------------------------

    def on_mouse_down(self, event: MouseDown) -> None:
        self._dragging = True
        self.add_class("dragging")
        self.capture_mouse()
        event.stop()

    def on_mouse_move(self, event: MouseMove) -> None:
        if not self._dragging:
            return
        new_width = self._clamped(event.screen_x)
        self.post_message(self.Resized(new_width, final=False))
        event.stop()

    def on_mouse_up(self, event: MouseUp) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.remove_class("dragging")
        self.release_mouse()
        new_width = self._clamped(event.screen_x)
        self.post_message(self.Resized(new_width, final=True))
        event.stop()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clamped(x: int) -> int:
        return max(_MIN_WIDTH, min(_MAX_WIDTH, x))
