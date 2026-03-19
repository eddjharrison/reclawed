"""SQLite persistence for messages and sessions."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from reclawed.crypto import decrypt_content, encrypt_content, is_encrypted
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
    def __init__(self, db_path: Path | str = ":memory:", local_key: bytes | None = None):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._local_key = local_key
        self._migrate()

    def _migrate(self) -> None:
        """Apply additive schema migrations that may not exist on older databases."""
        migrations = [
            "ALTER TABLE sessions ADD COLUMN muted INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN archived INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN unread_count INTEGER NOT NULL DEFAULT 0",
            # Group chat columns
            "ALTER TABLE sessions ADD COLUMN is_group INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN relay_url TEXT",
            "ALTER TABLE sessions ADD COLUMN room_id TEXT",
            "ALTER TABLE sessions ADD COLUMN participant_id TEXT",
            "ALTER TABLE sessions ADD COLUMN relay_token TEXT",
            # Per-message sender identity (group chat)
            "ALTER TABLE messages ADD COLUMN sender_name TEXT",
            "ALTER TABLE messages ADD COLUMN sender_type TEXT",
            # Message editing and soft deletion
            "ALTER TABLE messages ADD COLUMN edited_at TEXT",
            "ALTER TABLE messages ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0",
            # Encryption
            "ALTER TABLE sessions ADD COLUMN encryption_passphrase TEXT",
            "ALTER TABLE messages ADD COLUMN encrypted INTEGER NOT NULL DEFAULT 0",
            # Workspaces
            "ALTER TABLE sessions ADD COLUMN cwd TEXT",
            # Room modes
            "ALTER TABLE sessions ADD COLUMN room_mode TEXT",
            # Per-session permission mode
            "ALTER TABLE sessions ADD COLUMN permission_mode TEXT",
            # Context tracking
            "ALTER TABLE sessions ADD COLUMN last_input_tokens INTEGER NOT NULL DEFAULT 0",
            # Session pinning
            "ALTER TABLE sessions ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0",
            # Message attachments (JSON)
            "ALTER TABLE messages ADD COLUMN attachments TEXT",
            # Orchestrator / worker sessions
            "ALTER TABLE sessions ADD COLUMN parent_session_id TEXT",
            "ALTER TABLE sessions ADD COLUMN session_type TEXT",
            "ALTER TABLE sessions ADD COLUMN worker_status TEXT",
            "ALTER TABLE sessions ADD COLUMN worker_summary TEXT",
            # Worker template tracking
            "ALTER TABLE sessions ADD COLUMN worker_template_id TEXT",
        ]
        for sql in migrations:
            try:
                self._conn.execute(sql)
            except sqlite3.OperationalError:
                # Column already exists — safe to ignore.
                pass
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- Sessions ---

    def create_session(self, session: Session) -> Session:
        self._conn.execute(
            "INSERT INTO sessions (id, claude_session_id, name, created_at, updated_at, model, "
            "total_cost_usd, message_count, muted, archived, unread_count, "
            "is_group, relay_url, room_id, participant_id, relay_token, encryption_passphrase, "
            "cwd, room_mode, permission_mode, last_input_tokens, pinned, "
            "parent_session_id, session_type, worker_status, worker_summary, worker_template_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session.id, session.claude_session_id, session.name,
             _fmt_dt(session.created_at), _fmt_dt(session.updated_at),
             session.model, session.total_cost_usd, session.message_count,
             int(session.muted), int(session.archived), session.unread_count,
             int(session.is_group), session.relay_url, session.room_id, session.participant_id,
             session.relay_token, session.encryption_passphrase, session.cwd,
             session.room_mode, session.permission_mode, session.last_input_tokens,
             int(session.pinned), session.parent_session_id, session.session_type,
             session.worker_status, session.worker_summary, session.worker_template_id),
        )
        self._conn.commit()
        return session

    def get_session(self, session_id: str) -> Session | None:
        row = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def list_sessions(self, include_archived: bool = False) -> list[Session]:
        if include_archived:
            rows = self._conn.execute(
                "SELECT * FROM sessions ORDER BY pinned DESC, updated_at DESC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM sessions WHERE archived = 0 ORDER BY pinned DESC, updated_at DESC"
            ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def update_session(self, session: Session) -> None:
        session.updated_at = datetime.now(timezone.utc)
        self._conn.execute(
            "UPDATE sessions SET claude_session_id=?, name=?, updated_at=?, model=?, "
            "total_cost_usd=?, message_count=?, muted=?, archived=?, unread_count=?, "
            "is_group=?, relay_url=?, room_id=?, participant_id=?, relay_token=?, "
            "encryption_passphrase=?, cwd=?, room_mode=?, permission_mode=?, "
            "last_input_tokens=?, pinned=?, parent_session_id=?, session_type=?, "
            "worker_status=?, worker_summary=?, worker_template_id=? WHERE id=?",
            (session.claude_session_id, session.name, _fmt_dt(session.updated_at),
             session.model, session.total_cost_usd, session.message_count,
             int(session.muted), int(session.archived), session.unread_count,
             int(session.is_group), session.relay_url, session.room_id, session.participant_id,
             session.relay_token, session.encryption_passphrase, session.cwd,
             session.room_mode, session.permission_mode,
             session.last_input_tokens, int(session.pinned),
             session.parent_session_id, session.session_type,
             session.worker_status, session.worker_summary, session.worker_template_id, session.id),
        )
        self._conn.commit()

    def mark_session_read(self, session_id: str) -> None:
        """Set unread_count to 0 for the given session."""
        self._conn.execute(
            "UPDATE sessions SET unread_count = 0 WHERE id = ?", (session_id,)
        )
        self._conn.commit()

    def increment_unread(self, session_id: str) -> None:
        """Increment unread_count by 1 for the given session."""
        self._conn.execute(
            "UPDATE sessions SET unread_count = unread_count + 1 WHERE id = ?", (session_id,)
        )
        self._conn.commit()

    def list_sessions_by_cwd(self, cwd: str) -> list[Session]:
        """Return non-archived sessions matching the given working directory."""
        rows = self._conn.execute(
            "SELECT * FROM sessions WHERE cwd = ? AND archived = 0 ORDER BY updated_at DESC",
            (cwd,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def has_claude_session(self, claude_session_id: str) -> bool:
        """Return True if a session with this claude_session_id already exists."""
        row = self._conn.execute(
            "SELECT 1 FROM sessions WHERE claude_session_id = ? LIMIT 1",
            (claude_session_id,),
        ).fetchone()
        return row is not None

    def get_worker_sessions(self, parent_id: str) -> list[Session]:
        """Return non-archived worker sessions for the given orchestrator, ordered by created_at ASC."""
        rows = self._conn.execute(
            "SELECT * FROM sessions WHERE parent_session_id = ? AND archived = 0 "
            "ORDER BY created_at ASC",
            (parent_id,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

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
        stored_content = msg.content
        encrypted = 0
        if self._local_key:
            stored_content = encrypt_content(msg.content, self._local_key)
            encrypted = 1
        self._conn.execute(
            "INSERT INTO messages (id, seq, role, content, timestamp, session_id, claude_session_id, "
            "reply_to_id, bookmarked, cost_usd, duration_ms, model, input_tokens, output_tokens, "
            "sender_name, sender_type, encrypted, attachments) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (msg.id, msg.seq, msg.role, stored_content, _fmt_dt(msg.timestamp),
             msg.session_id, msg.claude_session_id, msg.reply_to_id,
             int(msg.bookmarked), msg.cost_usd, msg.duration_ms,
             msg.model, msg.input_tokens, msg.output_tokens,
             msg.sender_name, msg.sender_type, encrypted, msg.attachments),
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
        stored_content = msg.content
        encrypted = 0
        if self._local_key:
            stored_content = encrypt_content(msg.content, self._local_key)
            encrypted = 1
        self._conn.execute(
            "UPDATE messages SET content=?, bookmarked=?, cost_usd=?, duration_ms=?, model=?, "
            "input_tokens=?, output_tokens=?, claude_session_id=?, sender_name=?, sender_type=?, "
            "edited_at=?, deleted=?, encrypted=?, attachments=? WHERE id=?",
            (stored_content, int(msg.bookmarked), msg.cost_usd, msg.duration_ms,
             msg.model, msg.input_tokens, msg.output_tokens, msg.claude_session_id,
             msg.sender_name, msg.sender_type,
             _fmt_dt(msg.edited_at) if msg.edited_at else None,
             int(msg.deleted), encrypted, msg.attachments, msg.id),
        )
        self._conn.commit()

    def soft_delete_message(self, message_id: str) -> None:
        """Mark a message as deleted (soft delete)."""
        self._conn.execute(
            "UPDATE messages SET deleted = 1 WHERE id = ?", (message_id,)
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

    def get_last_message(self, session_id: str) -> Message | None:
        """Return the most recent message in the session, or None if empty."""
        row = self._conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY seq DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_message(row)

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
        if self._local_key:
            # With local encryption, SQL LIKE can't search ciphertext.
            # Fetch all non-deleted messages, decrypt, and filter in Python.
            if session_id:
                rows = self._conn.execute(
                    "SELECT * FROM messages WHERE session_id = ? "
                    "AND deleted = 0 ORDER BY seq",
                    (session_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM messages WHERE deleted = 0 "
                    "ORDER BY timestamp DESC",
                ).fetchall()
            messages = [self._row_to_message(r) for r in rows]
            lower_query = query.lower()
            return [m for m in messages if lower_query in m.content.lower()]

        like = f"%{query}%"
        if session_id:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE content LIKE ? AND session_id = ? "
                "AND deleted = 0 ORDER BY seq",
                (like, session_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE content LIKE ? AND deleted = 0 "
                "ORDER BY timestamp DESC",
                (like,),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def export_session_markdown(self, session_id: str) -> str:
        """Generate a markdown document from all messages in a session.

        Returns an empty string if the session does not exist.  Messages that
        have a ``reply_to_id`` include a blockquote showing a short excerpt of
        the parent message so the thread context is visible when reading the
        exported file.
        """
        session = self.get_session(session_id)
        if session is None:
            return ""

        messages = self.get_session_messages(session_id)

        # Build a lookup so we can resolve parent content in O(1).
        msg_by_id: dict[str, Message] = {m.id: m for m in messages}

        date_str = session.created_at.strftime("%Y-%m-%d")
        lines: list[str] = [
            f"# Session: {session.name}",
            f"*{date_str}*",
        ]

        for msg in messages:
            if msg.deleted:
                continue

            lines.append("")
            lines.append("---")
            lines.append("")

            if msg.reply_to_id:
                parent = msg_by_id.get(msg.reply_to_id)
                if parent:
                    excerpt = parent.content[:120].replace("\n", " ")
                    if len(parent.content) > 120:
                        excerpt += "..."
                    lines.append(f"> replying to: {excerpt}")
                    lines.append("")

            speaker = "You" if msg.role == "user" else "Claude"
            time_str = msg.timestamp.strftime("%H:%M")
            lines.append(f"**{speaker}** ({time_str})")
            lines.append(msg.content)

        lines.append("")
        return "\n".join(lines)

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
        keys = row.keys()
        edited_at_raw = row["edited_at"] if "edited_at" in keys else None
        content = row["content"]
        row_encrypted = bool(row["encrypted"]) if "encrypted" in keys else False
        if row_encrypted and self._local_key and is_encrypted(content):
            content = decrypt_content(content, self._local_key)
        return Message(
            id=row["id"],
            seq=row["seq"],
            role=row["role"],
            content=content,
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
            sender_name=row["sender_name"] if "sender_name" in keys else None,
            sender_type=row["sender_type"] if "sender_type" in keys else None,
            edited_at=_parse_dt(edited_at_raw) if edited_at_raw else None,
            deleted=bool(row["deleted"]) if "deleted" in keys else False,
            attachments=row["attachments"] if "attachments" in keys else None,
        )

    def _row_to_session(self, row: sqlite3.Row) -> Session:
        keys = row.keys()
        return Session(
            id=row["id"],
            claude_session_id=row["claude_session_id"],
            name=row["name"],
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
            model=row["model"],
            total_cost_usd=row["total_cost_usd"],
            message_count=row["message_count"],
            muted=bool(row["muted"]),
            archived=bool(row["archived"]),
            unread_count=row["unread_count"],
            is_group=bool(row["is_group"]) if "is_group" in keys else False,
            relay_url=row["relay_url"] if "relay_url" in keys else None,
            room_id=row["room_id"] if "room_id" in keys else None,
            participant_id=row["participant_id"] if "participant_id" in keys else None,
            relay_token=row["relay_token"] if "relay_token" in keys else None,
            encryption_passphrase=row["encryption_passphrase"] if "encryption_passphrase" in keys else None,
            cwd=row["cwd"] if "cwd" in keys else None,
            room_mode=row["room_mode"] if "room_mode" in keys else None,
            permission_mode=row["permission_mode"] if "permission_mode" in keys else None,
            last_input_tokens=row["last_input_tokens"] if "last_input_tokens" in keys else 0,
            pinned=bool(row["pinned"]) if "pinned" in keys else False,
            parent_session_id=row["parent_session_id"] if "parent_session_id" in keys else None,
            session_type=row["session_type"] if "session_type" in keys else None,
            worker_status=row["worker_status"] if "worker_status" in keys else None,
            worker_summary=row["worker_summary"] if "worker_summary" in keys else None,
            worker_template_id=row["worker_template_id"] if "worker_template_id" in keys else None,
        )
