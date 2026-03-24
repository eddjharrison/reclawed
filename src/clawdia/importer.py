"""Discover and import Claude Code sessions from ~/.claude/projects/."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from clawdia.models import Message, Session
from clawdia.store import Store

_SESSION_NAME_MAX = 60

# XML-style tags injected by Claude Code that aren't real user content.
_XML_TAG_RE = re.compile(r"<[^>]+>")
_SYSTEM_PREFIXES = (
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<command-name>",
    "<task-notification>",
    "<system-reminder>",
    "<file-history-snapshot>",
)


def _clean_user_text(raw: str) -> str | None:
    """Extract clean display text from a Claude Code user message.

    Returns ``None`` if the message is a system/command message that
    should be skipped when choosing a session name.
    """
    stripped = raw.strip()
    if not stripped:
        return None
    # Skip messages that are system injections, not real user input
    for prefix in _SYSTEM_PREFIXES:
        if stripped.startswith(prefix):
            return None
    # Skip slash-command wrappers (e.g. <command-name>/prompt</command-name>)
    if "<command-name>" in stripped:
        return None
    # Strip any remaining XML tags and clean up whitespace
    cleaned = _XML_TAG_RE.sub("", stripped).strip()
    # Collapse internal whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned if cleaned else None


@dataclass
class DiscoveredProject:
    """A project directory discovered under ~/.claude/projects/."""

    cwd: str  # real filesystem path, e.g. "/Users/ed/EIR/reclawed"
    session_count: int  # number of .jsonl files
    project_dir: Path  # full path to the project directory


def _claude_projects_dir() -> Path:
    """Return the default Claude Code projects directory."""
    return Path.home() / ".claude" / "projects"


def _extract_cwd_from_dir_name(encoded_name: str) -> str:
    """Decode a project directory name back to a filesystem path.

    Claude Code encodes paths by replacing ``/`` with ``-``, so
    ``-Users-ed-EIR-reclawed`` becomes ``/Users/ed/EIR/reclawed``.
    """
    return encoded_name.replace("-", "/")


def _extract_cwd_from_jsonl(project_dir: Path) -> str | None:
    """Read the cwd field from the first user message in any JSONL file."""
    for jsonl in sorted(project_dir.glob("*.jsonl"))[:3]:
        try:
            with jsonl.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("type") == "user" and entry.get("cwd"):
                        return entry["cwd"]
        except OSError:
            continue
    return None


def discover_projects(claude_dir: Path | None = None) -> list[DiscoveredProject]:
    """Scan ~/.claude/projects/ and return discovered projects.

    Parameters
    ----------
    claude_dir:
        Override the projects directory (useful in tests).

    Returns a list sorted by session count (most active first).
    """
    projects_dir = claude_dir or _claude_projects_dir()
    if not projects_dir.is_dir():
        return []

    results: list[DiscoveredProject] = []
    for subdir in sorted(projects_dir.iterdir()):
        if not subdir.is_dir():
            continue
        jsonl_files = list(subdir.glob("*.jsonl"))
        if not jsonl_files:
            continue

        # Try to get cwd from JSONL content first, fall back to dir name
        cwd = _extract_cwd_from_jsonl(subdir)
        if not cwd:
            cwd = _extract_cwd_from_dir_name(subdir.name)

        results.append(DiscoveredProject(
            cwd=cwd,
            session_count=len(jsonl_files),
            project_dir=subdir,
        ))

    results.sort(key=lambda p: p.session_count, reverse=True)
    return results


def parse_session_metadata(jsonl_path: Path) -> dict | None:
    """Extract metadata from a Claude Code JSONL transcript.

    Returns a dict with keys: ``session_id``, ``cwd``, ``name``,
    ``model``, ``created_at``, ``updated_at``.  Returns ``None`` if no
    usable user message is found.
    """
    session_id: str | None = None
    cwd: str | None = None
    name: str | None = None
    model: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    try:
        with jsonl_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = entry.get("type")

                # First real user message → session name + created_at
                # Skip system injections (local-command-caveat, etc.)
                if entry_type == "user" and name is None:
                    msg = entry.get("message", {})
                    content = msg.get("content", "")
                    text: str | None = None
                    if isinstance(content, str):
                        text = _clean_user_text(content)
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = _clean_user_text(block["text"])
                                if text:
                                    break
                    if text:
                        name = text
                        if len(name) > _SESSION_NAME_MAX:
                            name = name[:_SESSION_NAME_MAX - 1] + "…"
                        session_id = entry.get("sessionId")
                        cwd = entry.get("cwd")
                        created_at = entry.get("timestamp")

                # First assistant message → model
                if entry_type == "assistant" and model is None:
                    msg = entry.get("message", {})
                    model = msg.get("model")

                # Track last timestamp for updated_at
                ts = entry.get("timestamp")
                if ts:
                    updated_at = ts

                # Once we have everything, no need to keep reading
                if name and model:
                    # But keep going to find the last timestamp
                    pass
    except OSError:
        return None

    if not session_id or not name:
        return None

    return {
        "session_id": session_id,
        "cwd": cwd,
        "name": name,
        "model": model,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _parse_iso_timestamp(ts: str | None) -> datetime:
    """Parse an ISO 8601 timestamp, falling back to now."""
    if ts:
        try:
            return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc)


def import_project_sessions(
    project: DiscoveredProject,
    store: Store,
    max_sessions: int = 20,
) -> int:
    """Import recent sessions from a discovered project into the store.

    Returns the number of newly imported sessions.
    """
    jsonl_files = list(project.project_dir.glob("*.jsonl"))
    # Sort by modification time, most recent first
    jsonl_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    jsonl_files = jsonl_files[:max_sessions]

    imported = 0
    for jsonl_path in jsonl_files:
        meta = parse_session_metadata(jsonl_path)
        if meta is None:
            continue

        # Dedup: skip if this Claude session already exists
        if store.has_claude_session(meta["session_id"]):
            continue

        session = Session(
            claude_session_id=meta["session_id"],
            name=meta["name"],
            cwd=meta["cwd"] or project.cwd,
            model=meta["model"],
            created_at=_parse_iso_timestamp(meta["created_at"]),
            updated_at=_parse_iso_timestamp(meta["updated_at"]),
        )
        store.create_session(session)

        # Add a synthetic message so the session passes the sidebar's
        # message_count > 0 filter and gives the user a visual cue.
        store.add_message(Message(
            role="assistant",
            content="*Imported session — send a message to resume.*",
            session_id=session.id,
        ))

        imported += 1

    return imported
