"""Tests for reclawed.utils — cross-platform helpers."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from clawdia.utils import copy_to_clipboard, format_relative_time


# ---------------------------------------------------------------------------
# format_relative_time — cross-platform strftime fix
# ---------------------------------------------------------------------------


def test_format_timestamp_old_single_digit_day():
    """Single-digit days must not have a leading zero (cross-platform %-d fix)."""
    ts = datetime(2025, 3, 5, 12, 0, 0)
    result = format_relative_time(ts)
    assert result == "Mar 5", f"Expected 'Mar 5', got {result!r}"


def test_format_timestamp_old_double_digit_day():
    """Double-digit days are returned as-is."""
    ts = datetime(2025, 3, 15, 12, 0, 0)
    result = format_relative_time(ts)
    assert result == "Mar 15", f"Expected 'Mar 15', got {result!r}"


def test_format_timestamp_old_first_of_month():
    """The first of a month (day == 1) must show '1', not '01'."""
    ts = datetime(2025, 6, 1, 0, 0, 0)
    result = format_relative_time(ts)
    assert result == "Jun 1", f"Expected 'Jun 1', got {result!r}"


# ---------------------------------------------------------------------------
# copy_to_clipboard — cross-platform dispatch
# ---------------------------------------------------------------------------


def _make_run_ok(*args, **kwargs):
    """subprocess.run stub that always succeeds (returncode=0)."""
    import subprocess

    return subprocess.CompletedProcess(args=args[0], returncode=0)


def _make_run_fail(*args, **kwargs):
    """subprocess.run stub that raises FileNotFoundError."""
    raise FileNotFoundError("not found")


@patch("clawdia.utils.platform.system", return_value="Darwin")
@patch("clawdia.utils.subprocess.run", side_effect=_make_run_ok)
def test_copy_clipboard_macos_success(mock_run, mock_system):
    """On macOS, pbcopy is invoked and True is returned on success."""
    result = copy_to_clipboard("hello")
    assert result is True
    cmd = mock_run.call_args[0][0]
    assert cmd == ["pbcopy"]


@patch("clawdia.utils.platform.system", return_value="Windows")
@patch("clawdia.utils.subprocess.run", side_effect=_make_run_ok)
def test_copy_clipboard_windows_success(mock_run, mock_system):
    """On Windows, clip.exe is invoked and True is returned on success."""
    result = copy_to_clipboard("hello")
    assert result is True
    cmd = mock_run.call_args[0][0]
    assert cmd == ["clip.exe"]


@patch("clawdia.utils.platform.system", return_value="Linux")
@patch("clawdia.utils.subprocess.run", side_effect=_make_run_ok)
def test_copy_clipboard_linux_xclip_success(mock_run, mock_system):
    """On Linux, xclip is tried first and True is returned on success."""
    result = copy_to_clipboard("hello")
    assert result is True
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "xclip"


@patch("clawdia.utils.platform.system", return_value="Linux")
def test_copy_clipboard_linux_falls_back_to_xsel(mock_system):
    """On Linux, if xclip is absent, xsel is tried next."""
    import subprocess

    call_log: list[list[str]] = []

    def selective_fail(*args, **kwargs):
        cmd = args[0]
        call_log.append(cmd)
        if cmd[0] == "xclip":
            raise FileNotFoundError("xclip not found")
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    with patch("clawdia.utils.subprocess.run", side_effect=selective_fail):
        result = copy_to_clipboard("hello")

    assert result is True
    assert call_log[0][0] == "xclip"
    assert call_log[1][0] == "xsel"


@patch("clawdia.utils.platform.system", return_value="Linux")
@patch("clawdia.utils.subprocess.run", side_effect=FileNotFoundError("nothing"))
def test_copy_clipboard_all_fail_returns_false(mock_run, mock_system):
    """Returns False when every clipboard candidate is unavailable."""
    result = copy_to_clipboard("hello")
    assert result is False


@patch("clawdia.utils.platform.system", return_value="Darwin")
@patch("clawdia.utils.subprocess.run", side_effect=FileNotFoundError("no pbcopy"))
def test_copy_clipboard_macos_missing_pbcopy(mock_run, mock_system):
    """Returns False on macOS when pbcopy is not installed."""
    result = copy_to_clipboard("hello")
    assert result is False


def test_copy_clipboard_encodes_unicode():
    """Unicode text is encoded to UTF-8 before being passed to subprocess."""
    captured: list[bytes] = []

    def capture_input(*args, **kwargs):
        import subprocess
        captured.append(kwargs.get("input", b""))
        return subprocess.CompletedProcess(args=args[0], returncode=0)

    with patch("clawdia.utils.platform.system", return_value="Darwin"):
        with patch("clawdia.utils.subprocess.run", side_effect=capture_input):
            copy_to_clipboard("caf\u00e9")

    assert captured[0] == "café".encode("utf-8")
