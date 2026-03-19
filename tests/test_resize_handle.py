"""Tests for SidebarResizeHandle clamping logic and Resized message."""

from __future__ import annotations

import pytest

from reclawed.widgets.resize_handle import SidebarResizeHandle, _MIN_WIDTH, _MAX_WIDTH


# ---------------------------------------------------------------------------
# _clamped — the core width-clamping helper
# ---------------------------------------------------------------------------


class TestClamped:
    def test_within_range_unchanged(self):
        """Values inside [MIN, MAX] are returned unchanged."""
        assert SidebarResizeHandle._clamped(35) == 35

    def test_exactly_min(self):
        """Value equal to _MIN_WIDTH is returned as-is."""
        assert SidebarResizeHandle._clamped(_MIN_WIDTH) == _MIN_WIDTH

    def test_exactly_max(self):
        """Value equal to _MAX_WIDTH is returned as-is."""
        assert SidebarResizeHandle._clamped(_MAX_WIDTH) == _MAX_WIDTH

    def test_below_min_clamped_to_min(self):
        """Values below _MIN_WIDTH are clamped to _MIN_WIDTH."""
        assert SidebarResizeHandle._clamped(0) == _MIN_WIDTH
        assert SidebarResizeHandle._clamped(1) == _MIN_WIDTH
        assert SidebarResizeHandle._clamped(_MIN_WIDTH - 1) == _MIN_WIDTH

    def test_above_max_clamped_to_max(self):
        """Values above _MAX_WIDTH are clamped to _MAX_WIDTH."""
        assert SidebarResizeHandle._clamped(_MAX_WIDTH + 1) == _MAX_WIDTH
        assert SidebarResizeHandle._clamped(200) == _MAX_WIDTH
        assert SidebarResizeHandle._clamped(9999) == _MAX_WIDTH

    def test_negative_clamped_to_min(self):
        """Negative x values (dragged far left) are clamped to _MIN_WIDTH."""
        assert SidebarResizeHandle._clamped(-100) == _MIN_WIDTH

    def test_constants_sensible(self):
        """_MIN_WIDTH and _MAX_WIDTH are positive and MIN < MAX."""
        assert _MIN_WIDTH > 0
        assert _MAX_WIDTH > _MIN_WIDTH

    def test_midpoint_unchanged(self):
        """A value exactly halfway between min and max is unchanged."""
        mid = (_MIN_WIDTH + _MAX_WIDTH) // 2
        assert SidebarResizeHandle._clamped(mid) == mid


# ---------------------------------------------------------------------------
# Resized message
# ---------------------------------------------------------------------------


class TestResizedMessage:
    def test_new_width_stored(self):
        """Resized message stores the new_width value."""
        msg = SidebarResizeHandle.Resized(new_width=42)
        assert msg.new_width == 42

    def test_final_defaults_to_false(self):
        """Resized.final defaults to False (mid-drag)."""
        msg = SidebarResizeHandle.Resized(new_width=30)
        assert msg.final is False

    def test_final_true_on_release(self):
        """Resized.final=True signals the final mouse-up event."""
        msg = SidebarResizeHandle.Resized(new_width=30, final=True)
        assert msg.final is True

    def test_final_false_explicit(self):
        """Resized.final=False can be set explicitly."""
        msg = SidebarResizeHandle.Resized(new_width=25, final=False)
        assert msg.final is False

    def test_min_width_message(self):
        """Resized message works with clamped minimum width."""
        msg = SidebarResizeHandle.Resized(new_width=_MIN_WIDTH, final=True)
        assert msg.new_width == _MIN_WIDTH
        assert msg.final is True

    def test_max_width_message(self):
        """Resized message works with clamped maximum width."""
        msg = SidebarResizeHandle.Resized(new_width=_MAX_WIDTH, final=True)
        assert msg.new_width == _MAX_WIDTH
        assert msg.final is True


# ---------------------------------------------------------------------------
# SidebarResizeHandle instantiation
# ---------------------------------------------------------------------------


class TestSidebarResizeHandleInit:
    def test_dragging_starts_false(self):
        """_dragging flag initialises to False (not dragging on creation)."""
        handle = SidebarResizeHandle()
        assert handle._dragging is False

    def test_multiple_instances_independent_state(self):
        """Two handles have independent _dragging state (no class-level sharing)."""
        h1 = SidebarResizeHandle()
        h2 = SidebarResizeHandle()
        h1._dragging = True
        assert h2._dragging is False

    def test_clamped_is_static(self):
        """_clamped is a static method callable without an instance."""
        # Should not raise
        result = SidebarResizeHandle._clamped(50)
        assert isinstance(result, int)
