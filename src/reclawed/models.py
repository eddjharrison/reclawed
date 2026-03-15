"""Data models for messages and sessions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str
    session_id: str
    id: str = field(default_factory=_new_id)
    seq: int = 0
    timestamp: datetime = field(default_factory=_now)
    claude_session_id: str | None = None
    reply_to_id: str | None = None
    bookmarked: bool = False
    cost_usd: float | None = None
    duration_ms: int | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class Session:
    id: str = field(default_factory=_new_id)
    claude_session_id: str | None = None
    name: str = "New Chat"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    model: str | None = None
    total_cost_usd: float = 0.0
    message_count: int = 0
    muted: bool = False
    archived: bool = False
    unread_count: int = 0
