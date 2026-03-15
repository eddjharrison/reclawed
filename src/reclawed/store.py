"""SQLite persistence for messages and sessions."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from reclawed.models import Message, Session

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    claude_session_id TEXT,
    name TEXT NOT NULL DEFAULT 'New Chat',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    model TEXT,
    total_cost_usd REAL NOT NULL DEFAULT 0.0,
    message_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    claude_session_id TEXT,
    reply_to_id TEXT REFERENCES messages(id),
    bookmarked INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL,
    duration_ms INTEGER,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_messages_reply ON messages(reply_to_id);
CREATE INDEX IF NOT EXISTS idx_messages_bookmarked ON messages(bookmarked) WHERE bookmarked = 1;
"""


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _fmt_dt(dt: datetime) -> str:
    return dt.isoformat()


class Store:
    def __init__(self, db_path: Path | str = ":memory:"):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- Sessions ---

    def create_session(self, session: Session) -> Session:
        self._conn.execute(
            "INSERT INTO sessions (id, claude_session_id, name, created_at, updated_at, model, total_cost_usd, message_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session.id, session.claude_session_id, session.name,
             _fmt_dt(session.created_at), _fmt_dt(session.updated_at),
             session.model, session.total_cost_usd, session.message_count),
        )
        self._conn.commit()
        return session

    def get_session(self, session_id: str) -> Session | None:
        row = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def list_sessions(self) -> list[Session]:
        rows = self._conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
        return [self._row_to_session(r) for r in rows]

    def update_session(self, session: Session) -> None:
        session.updated_at = datetime.now(timezone.utc)
        self._conn.execute(
            "UPDATE sessions SET claude_session_id=?, name=?, updated_at=?, model=?, total_cost_usd=?, message_count=? WHERE id=?",
            (session.claude_session_id, session.name, _fmt_dt(session.updated_at),
             session.model, session.total_cost_usd, session.message_count, session.id),
        )
        self._conn.commit()

    def delete_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()

    # --- Messages ---

    def add_message(self, msg: Message) -> Message:
        if msg.seq == 0:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE session_id = ?",
                (msg.session_id,),
            ).fetchone()
            msg.seq = row[0]
        self._conn.execute(
            "INSERT INTO messages (id, seq, role, content, timestamp, session_id, claude_session_id, "
            "reply_to_id, bookmarked, cost_usd, duration_ms, model, input_tokens, output_tokens) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (msg.id, msg.seq, msg.role, msg.content, _fmt_dt(msg.timestamp),
             msg.session_id, msg.claude_session_id, msg.reply_to_id,
             int(msg.bookmarked), msg.cost_usd, msg.duration_ms,
             msg.model, msg.input_tokens, msg.output_tokens),
        )
        self._conn.commit()
        # Update session message count
        self._conn.execute(
            "UPDATE sessions SET message_count = message_count + 1, updated_at = ? WHERE id = ?",
            (_fmt_dt(datetime.now(timezone.utc)), msg.session_id),
        )
        self._conn.commit()
        return msg

    def update_message(self, msg: Message) -> None:
        self._conn.execute(
            "UPDATE messages SET content=?, bookmarked=?, cost_usd=?, duration_ms=?, model=?, "
            "input_tokens=?, output_tokens=?, claude_session_id=? WHERE id=?",
            (msg.content, int(msg.bookmarked), msg.cost_usd, msg.duration_ms,
             msg.model, msg.input_tokens, msg.output_tokens, msg.claude_session_id, msg.id),
        )
        self._conn.commit()

    def get_message(self, message_id: str) -> Message | None:
        row = self._conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_message(row)

    def get_session_messages(self, session_id: str) -> list[Message]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY seq", (session_id,)
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def get_bookmarked_messages(self, session_id: str | None = None) -> list[Message]:
        if session_id:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE bookmarked = 1 AND session_id = ? ORDER BY seq",
                (session_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE bookmarked = 1 ORDER BY timestamp DESC"
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def search_messages(self, query: str, session_id: str | None = None) -> list[Message]:
        like = f"%{query}%"
        if session_id:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE content LIKE ? AND session_id = ? ORDER BY seq",
                (like, session_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE content LIKE ? ORDER BY timestamp DESC",
                (like,),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def get_reply_chain(self, message_id: str) -> list[Message]:
        chain: list[Message] = []
        current_id: str | None = message_id
        while current_id:
            msg = self.get_message(current_id)
            if msg is None:
                break
            chain.append(msg)
            current_id = msg.reply_to_id
        chain.reverse()
        return chain

    # --- Helpers ---

    def _row_to_message(self, row: sqlite3.Row) -> Message:
        return Message(
            id=row["id"],
            seq=row["seq"],
            role=row["role"],
            content=row["content"],
            timestamp=_parse_dt(row["timestamp"]),
            session_id=row["session_id"],
            claude_session_id=row["claude_session_id"],
            reply_to_id=row["reply_to_id"],
            bookmarked=bool(row["bookmarked"]),
            cost_usd=row["cost_usd"],
            duration_ms=row["duration_ms"],
            model=row["model"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
        )

    def _row_to_session(self, row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            claude_session_id=row["claude_session_id"],
            name=row["name"],
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
            model=row["model"],
            total_cost_usd=row["total_cost_usd"],
            message_count=row["message_count"],
        )
