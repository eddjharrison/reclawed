"""Shared utility helpers."""

from __future__ import annotations

import platform
import subprocess
from datetime import datetime


def format_relative_time(ts: datetime) -> str:
    """Return a human-readable relative timestamp.

    Rules:
      < 1 minute  -> "just now"
      < 1 hour    -> "Xm ago"
      < 24 hours  -> "Xh ago"
      otherwise   -> abbreviated date, e.g. "Mar 15"
    """
    # Make both sides timezone-aware or both naive for safe subtraction.
    now = datetime.now(tz=ts.tzinfo) if ts.tzinfo is not None else datetime.now()
    delta_seconds = (now - ts).total_seconds()

    if delta_seconds < 60:
        return "just now"
    if delta_seconds < 3600:
        return f"{int(delta_seconds // 60)}m ago"
    if delta_seconds < 86400:
        return f"{int(delta_seconds // 3600)}h ago"

    # %-d (no-padding day) is Linux/macOS only; %#d is Windows only.
    # Use %d and strip the leading zero manually for cross-platform compatibility.
    month = ts.strftime("%b")
    day = ts.strftime("%d").lstrip("0") or "0"
    return f"{month} {day}"


def copy_to_clipboard(text: str) -> bool:
    """Copy *text* to the system clipboard.

    Tries the appropriate clipboard tool for the current platform and returns
    ``True`` on success, ``False`` if no supported tool was found or the
    subprocess call failed.

    Platform support:
      - macOS: ``pbcopy``
      - Windows: ``clip.exe``
      - Linux / other: ``xclip -selection clipboard``, then ``xsel --clipboard --input``
    """
    system = platform.system()
    encoded = text.encode("utf-8")

    if system == "Darwin":
        candidates = [["pbcopy"]]
    elif system == "Windows":
        candidates = [["clip.exe"]]
    else:
        # Linux and any other POSIX system — try xclip first, then xsel.
        candidates = [
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ]

    for cmd in candidates:
        try:
            subprocess.run(cmd, input=encoded, check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue

    return False
