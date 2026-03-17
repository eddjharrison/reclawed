"""Shared utility helpers."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import platform
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


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


def detect_question(text: str) -> bool:
    """Detect if the assistant's response ends with a question.

    Checks the last paragraph — if it ends with ``?`` and is not inside
    a code block, it's treated as a question.
    """
    clean = text.rstrip()
    if not clean:
        return False
    # Ignore trailing code blocks
    if clean.endswith("```"):
        return False
    last_para = clean.split("\n\n")[-1].strip()
    return last_para.endswith("?")


_CHOICE_PATTERN = re.compile(r"^(?:(\d+)\.|([a-zA-Z])[\.\)])[\s]+(.+)$")


def detect_choices(text: str) -> list[tuple[str, str]]:
    """Detect numbered or lettered choices in text.

    Returns a list of ``(label, description)`` tuples, e.g.::

        [("1", "Use React"), ("2", "Use Vue"), ("3", "Use Svelte")]

    Only returns results when 2+ sequential choices are found.
    """
    choices: list[tuple[str, str]] = []
    for line in text.splitlines():
        m = _CHOICE_PATTERN.match(line.strip())
        if m:
            label = m.group(1) or m.group(2)
            description = m.group(3).strip()
            choices.append((label, description))
    return choices if len(choices) >= 2 else []


# ---------------------------------------------------------------------------
# Image / attachment helpers
# ---------------------------------------------------------------------------

# Supported image types for Claude multimodal input
IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
}

# Max file size for image attachments (20 MB — Anthropic API limit)
MAX_IMAGE_SIZE = 20 * 1024 * 1024


def is_image_file(path: str | Path) -> bool:
    """Check if a file path points to a supported image type."""
    ext = Path(path).suffix.lower()
    return ext in IMAGE_MIME_TYPES


def get_image_mime(path: str | Path) -> str:
    """Return the MIME type for an image file, or a sensible default."""
    ext = Path(path).suffix.lower()
    return IMAGE_MIME_TYPES.get(ext, "application/octet-stream")


def image_to_base64(path: str | Path) -> str:
    """Read an image file and return its base64-encoded contents."""
    return base64.standard_b64encode(Path(path).read_bytes()).decode("ascii")


def make_attachment_json(paths: list[str | Path]) -> str | None:
    """Build the JSON attachment metadata string for a list of file paths.

    Returns ``None`` if *paths* is empty.  Each entry has::

        {"path": str, "filename": str, "mime_type": str, "size_bytes": int}
    """
    if not paths:
        return None
    entries = []
    for p in paths:
        p = Path(p)
        entries.append({
            "path": str(p),
            "filename": p.name,
            "mime_type": get_image_mime(p),
            "size_bytes": p.stat().st_size,
        })
    return json.dumps(entries)


def parse_attachments(json_str: str | None) -> list[dict]:
    """Parse the JSON attachment string back into a list of dicts."""
    if not json_str:
        return []
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return []


def grab_clipboard_image() -> Path | None:
    """Try to grab an image from the system clipboard.

    Returns a temporary file path if an image was found, ``None`` otherwise.
    Works on Windows, macOS, and Linux (with xclip).
    """
    system = platform.system()

    if system == "Windows":
        return _grab_clipboard_image_windows()
    elif system == "Darwin":
        return _grab_clipboard_image_macos()
    else:
        return _grab_clipboard_image_linux()


def _grab_clipboard_image_windows() -> Path | None:
    """Windows: Use PowerShell to grab clipboard image."""
    tmp = Path(tempfile.gettempdir()) / "reclawed_clipboard.png"
    # PowerShell script to save clipboard image
    ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
$img = [System.Windows.Forms.Clipboard]::GetImage()
if ($img -ne $null) {{
    $img.Save('{tmp}', [System.Drawing.Imaging.ImageFormat]::Png)
    Write-Output 'OK'
}} else {{
    Write-Output 'NONE'
}}
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        if "OK" in result.stdout and tmp.exists() and tmp.stat().st_size > 0:
            return tmp
    except Exception:
        pass
    return None


def _grab_clipboard_image_macos() -> Path | None:
    """macOS: Use pngpaste or osascript to grab clipboard image."""
    tmp = Path(tempfile.gettempdir()) / "reclawed_clipboard.png"
    # Try pngpaste first (homebrew: brew install pngpaste)
    try:
        subprocess.run(["pngpaste", str(tmp)], check=True, capture_output=True, timeout=5)
        if tmp.exists() and tmp.stat().st_size > 0:
            return tmp
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # Fallback: osascript
    script = f'''
    set tmpPath to POSIX file "{tmp}"
    try
        set imgData to the clipboard as «class PNGf»
        set fRef to open for access tmpPath with write permission
        write imgData to fRef
        close access fRef
        return "OK"
    on error
        return "NONE"
    end try
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5,
        )
        if "OK" in result.stdout and tmp.exists() and tmp.stat().st_size > 0:
            return tmp
    except Exception:
        pass
    return None


def _grab_clipboard_image_linux() -> Path | None:
    """Linux: Use xclip to grab clipboard image."""
    tmp = Path(tempfile.gettempdir()) / "reclawed_clipboard.png"
    try:
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
            capture_output=True, timeout=5,
        )
        if result.returncode == 0 and len(result.stdout) > 0:
            tmp.write_bytes(result.stdout)
            return tmp
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # Try wl-paste for Wayland
    try:
        result = subprocess.run(
            ["wl-paste", "--type", "image/png"],
            capture_output=True, timeout=5,
        )
        if result.returncode == 0 and len(result.stdout) > 0:
            tmp.write_bytes(result.stdout)
            return tmp
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    return None


def format_file_size(size_bytes: int) -> str:
    """Format a file size as a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
