"""Re:Clawed relay server — broadcast WebSocket hub with SQLite message log.

Run directly:
    python -m reclawed.relay.server --port 8765 --token secret

Or via the installed entry point:
    reclawed-relay --port 8765 --token secret
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import click
import websockets
from websockets.asyncio.server import ServerConnection, serve

from reclawed.relay.protocol import RelayMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

@dataclass
class _ClientState:
    ws: ServerConnection
    room_id: str
    participant_id: str
    participant_name: str
    participant_type: str  # "human" | "claude"


# Maps room_id -> {participant_id -> _ClientState}
_rooms: dict[str, dict[str, _ClientState]] = {}

# Monotonic seq counter per room
_room_seqs: dict[str, int] = {}


def _next_seq(room_id: str) -> int:
    _room_seqs[room_id] = _room_seqs.get(room_id, 0) + 1
    return _room_seqs[room_id]


# ---------------------------------------------------------------------------
# SQLite message log (optional store-and-forward)
# ---------------------------------------------------------------------------

_db: sqlite3.Connection | None = None


def _init_db(path: str) -> None:
    global _db
    _db = sqlite3.connect(path, check_same_thread=False)
    _db.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            seq        INTEGER PRIMARY KEY,
            room_id    TEXT NOT NULL,
            message_id TEXT NOT NULL UNIQUE,
            payload    TEXT NOT NULL
        )
        """
    )
    _db.execute("CREATE INDEX IF NOT EXISTS idx_room_seq ON messages (room_id, seq)")
    _db.commit()
    # Seed seq counters from persisted state so they survive restarts.
    for row in _db.execute("SELECT room_id, MAX(seq) FROM messages GROUP BY room_id"):
        _room_seqs[row[0]] = row[1]
    logger.info("SQLite message log opened at %s", path)


def _persist(msg: RelayMessage) -> None:
    if _db is None:
        return
    try:
        _db.execute(
            "INSERT OR IGNORE INTO messages (seq, room_id, message_id, payload) VALUES (?, ?, ?, ?)",
            (msg.seq, msg.room_id, msg.message_id, msg.to_json()),
        )
        _db.commit()
    except Exception:
        logger.exception("Failed to persist message seq=%d", msg.seq)


def _messages_since(room_id: str, since_seq: int) -> list[str]:
    if _db is None:
        return []
    rows = _db.execute(
        "SELECT payload FROM messages WHERE room_id = ? AND seq > ? ORDER BY seq",
        (room_id, since_seq),
    ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Presence helpers
# ---------------------------------------------------------------------------

def _build_participants(room_id: str) -> list[dict[str, Any]]:
    room = _rooms.get(room_id, {})
    return [
        {
            "id": c.participant_id,
            "name": c.participant_name,
            "type": c.participant_type,
        }
        for c in room.values()
    ]


async def _broadcast_presence(room_id: str, event_type: str, trigger: _ClientState) -> None:
    """Send a presence message to everyone currently in the room."""
    now = datetime.now(timezone.utc).isoformat()
    msg = RelayMessage(
        type=event_type,
        room_id=room_id,
        sender_id=trigger.participant_id,
        sender_name=trigger.participant_name,
        sender_type=trigger.participant_type,
        timestamp=now,
        participants=_build_participants(room_id),
    )
    await _broadcast(room_id, msg.to_json())


async def _broadcast(room_id: str, payload: str, exclude: str | None = None) -> None:
    """Send a raw JSON payload to all clients in *room_id*, optionally skipping one."""
    room = _rooms.get(room_id, {})
    dead: list[str] = []
    for pid, client in room.items():
        if pid == exclude:
            continue
        try:
            await client.ws.send(payload)
        except websockets.exceptions.ConnectionClosed:
            dead.append(pid)
    for pid in dead:
        room.pop(pid, None)


# ---------------------------------------------------------------------------
# Connection handler  (modern websockets asyncio API — single ws argument)
# ---------------------------------------------------------------------------

async def _handler(ws: ServerConnection, *, shared_token: str | None = None) -> None:
    """Lifecycle handler for a single WebSocket connection."""
    # In websockets >=14 the request path is on ws.request.path
    raw_path = ws.request.path if hasattr(ws, "request") and ws.request else "/"
    parsed = urlparse(raw_path)
    params = parse_qs(parsed.query)

    # --- Auth ---
    if shared_token is not None:
        token = (params.get("token") or [""])[0]
        if token != shared_token:
            await ws.close(4001, "Unauthorised")
            logger.warning("Rejected connection with bad token")
            return

    # --- Required query params ---
    try:
        room_id = params["room_id"][0]
        participant_id = params["participant_id"][0]
        participant_name = params["participant_name"][0]
        participant_type = params.get("participant_type", ["human"])[0]
    except KeyError as exc:
        await ws.close(4002, f"Missing query param: {exc}")
        return

    client = _ClientState(
        ws=ws,
        room_id=room_id,
        participant_id=participant_id,
        participant_name=participant_name,
        participant_type=participant_type,
    )

    # Register client
    if room_id not in _rooms:
        _rooms[room_id] = {}
    _rooms[room_id][participant_id] = client
    logger.info("join room=%s participant=%s (%s)", room_id, participant_id, participant_name)

    # Send join presence to everyone (including new client so they see themselves)
    await _broadcast_presence(room_id, "join", client)

    try:
        async for raw in ws:
            await _handle_message(client, raw)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        _rooms.get(room_id, {}).pop(participant_id, None)
        logger.info("leave room=%s participant=%s", room_id, participant_id)
        if room_id in _rooms:
            await _broadcast_presence(room_id, "leave", client)


async def _handle_message(client: _ClientState, raw: str | bytes) -> None:
    try:
        msg = RelayMessage.from_json(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        err = RelayMessage(
            type="error",
            room_id=client.room_id,
            sender_id="server",
            sender_name="server",
            sender_type="human",
            timestamp=datetime.now(timezone.utc).isoformat(),
            error=f"Malformed message: {exc}",
        )
        await client.ws.send(err.to_json())
        return

    msg_type = msg.type

    if msg_type == "heartbeat":
        await client.ws.send(msg.to_json())
        return

    if msg_type == "sync_request":
        since = msg.seq
        payloads = _messages_since(client.room_id, since)
        response = RelayMessage(
            type="sync_response",
            room_id=client.room_id,
            sender_id="server",
            sender_name="server",
            sender_type="human",
            timestamp=datetime.now(timezone.utc).isoformat(),
            seq=len(payloads),
            content=json.dumps(payloads),
        )
        await client.ws.send(response.to_json())
        return

    if msg_type == "message":
        msg.seq = _next_seq(client.room_id)
        msg.room_id = client.room_id
        payload = msg.to_json()
        _persist(msg)
        await _broadcast(client.room_id, payload)
        return

    if msg_type in ("edit", "delete"):
        msg.seq = _next_seq(client.room_id)
        msg.room_id = client.room_id
        payload = msg.to_json()
        _persist(msg)
        await _broadcast(client.room_id, payload)
        return

    if msg_type in ("typing", "read"):
        # Ephemeral: broadcast without seq or persistence
        msg.room_id = client.room_id
        payload = msg.to_json()
        await _broadcast(client.room_id, payload, exclude=client.participant_id)
        return

    err = RelayMessage(
        type="error",
        room_id=client.room_id,
        sender_id="server",
        sender_name="server",
        sender_type="human",
        timestamp=datetime.now(timezone.utc).isoformat(),
        error=f"Unknown message type: {msg_type!r}",
    )
    await client.ws.send(err.to_json())


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.command()
@click.option("--host", default="0.0.0.0", show_default=True, help="Interface to bind")
@click.option("--port", default=8765, show_default=True, help="TCP port to listen on")
@click.option("--token", default=None, envvar="RELAY_TOKEN", help="Shared room token for auth")
@click.option("--db", "db_path", default=None, envvar="RELAY_DB", help="SQLite file for message log (omit to disable)")
@click.option("--log-level", default="INFO", show_default=True, help="Logging level")
def main(host: str, port: int, token: str | None, db_path: str | None, log_level: str) -> None:
    """Start the Re:Clawed WebSocket relay server."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if db_path:
        _init_db(db_path)

    import functools
    handler = functools.partial(_handler, shared_token=token)

    async def _serve() -> None:
        async with serve(handler, host, port):
            logger.info("Re:Clawed relay listening on ws://%s:%d", host, port)
            await asyncio.Future()  # run forever

    asyncio.run(_serve())


if __name__ == "__main__":
    main()
