"""Shared utility helpers."""

from __future__ import annotations

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
    return ts.strftime("%b %-d")
