"""Async WebSocket client for the Re:Clawed relay server.

Usage example (asyncio)::

    client = RelayClient(
        url="ws://localhost:8765",
        room_id="room-abc",
        participant_id="user-1",
        participant_name="Alice",
        token="secret",
    )
    await client.connect()
    await client.send_message("Hello, room!")
    async for msg in client.receive_messages():
        print(msg)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from websockets.asyncio.client import connect

from reclawed.crypto import decrypt_content, encrypt_content, is_encrypted
from reclawed.relay.protocol import RelayMessage

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 30  # seconds
_BACKOFF_BASE = 1         # seconds
_BACKOFF_MAX = 30         # seconds


class RelayClient:
    """Auto-reconnecting async client for the Re:Clawed relay server.

    The client maintains a single background task that owns the WebSocket
    connection and feeds received messages into an asyncio.Queue.  Callers
    consume that queue via ``receive_messages()``.

    Thread-safety: ``send_message`` is safe to call from any coroutine; it
    acquires a lock before writing to the socket.
    """

    def __init__(
        self,
        url: str,
        room_id: str,
        participant_id: str,
        participant_name: str,
        participant_type: str = "human",
        token: str | None = None,
        room_key: bytes | None = None,
    ) -> None:
        self._url = url
        self._room_id = room_id
        self._participant_id = participant_id
        self._participant_name = participant_name
        self._participant_type = participant_type
        self._token = token
        self._room_key = room_key

        self._ws: Any | None = None
        self._connected = asyncio.Event()
        self._disconnected = asyncio.Event()
        self._disconnected.set()  # starts disconnected
        self._send_lock = asyncio.Lock()
        self._recv_queue: asyncio.Queue[RelayMessage] = asyncio.Queue()
        self._participants: list[dict[str, Any]] = []
        self._last_seq: int = 0
        self._running = False
        self._bg_task: asyncio.Task[None] | None = None
        self._last_typing_sent: float = 0.0  # debounce typing signals
        self._last_read_sent: int = 0  # dedup read receipts
        self._status_callback: Any | None = None  # Callable[[str, int], None]
        self._reconnect_attempt: int = 0
        self._seen_message_ids: set[str] = set()  # dedup for sync_response replay

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def connect(self, timeout: float = 10.0) -> None:
        """Start the background receive/reconnect loop and wait for the first
        successful connection before returning.

        Raises ``TimeoutError`` if the connection is not established within
        *timeout* seconds.
        """
        if self._running:
            return
        self._running = True
        self._bg_task = asyncio.create_task(self._run(), name="relay-client")
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            # Don't leave the background task running if we timed out
            self._running = False
            if self._bg_task:
                self._bg_task.cancel()
                try:
                    await self._bg_task
                except asyncio.CancelledError:
                    pass
                self._bg_task = None
            raise TimeoutError(f"Could not connect to relay within {timeout}s")

    async def disconnect(self) -> None:
        """Gracefully close the connection and stop the background loop."""
        self._running = False
        if self._ws is not None:
            await self._ws.close()
        if self._bg_task is not None:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
        self._bg_task = None
        logger.info("RelayClient disconnected from room %s", self._room_id)
        if self._status_callback:
            try:
                self._status_callback("disconnected", 0)
            except Exception:
                pass

    async def send_message(
        self,
        content: str,
        sender_type: str | None = None,
        reply_to_seq: int | None = None,
        sender_name_override: str | None = None,
    ) -> None:
        """Send a chat message to the room.

        Raises ``RuntimeError`` if not connected.
        """
        if not self.is_connected:
            raise RuntimeError("RelayClient is not connected")
        wire_content = encrypt_content(content, self._room_key) if self._room_key else content
        msg = RelayMessage(
            type="message",
            room_id=self._room_id,
            sender_id=self._participant_id,
            sender_name=sender_name_override or self._participant_name,
            sender_type=sender_type or self._participant_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            content=wire_content,
            reply_to_seq=reply_to_seq,
            message_id=str(uuid.uuid4()),
        )
        async with self._send_lock:
            assert self._ws is not None  # guarded by is_connected check above
            await self._ws.send(msg.to_json())

    def set_status_callback(self, callback: Any) -> None:
        """Set a callback invoked on connection state changes.

        The callback receives (status: str, attempt: int) where status is one of
        "connected", "reconnecting", or "disconnected".
        """
        self._status_callback = callback

    async def send_typing(self) -> None:
        """Send a typing indicator, debounced to at most once every 3 seconds."""
        import time as _time

        now = _time.monotonic()
        if now - self._last_typing_sent < 3.0:
            return
        if not self.is_connected:
            return
        self._last_typing_sent = now
        msg = RelayMessage(
            type="typing",
            room_id=self._room_id,
            sender_id=self._participant_id,
            sender_name=self._participant_name,
            sender_type=self._participant_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        async with self._send_lock:
            assert self._ws is not None
            await self._ws.send(msg.to_json())

    async def send_read_receipt(self, seq: int) -> None:
        """Send a read receipt for messages up to *seq*, with deduplication."""
        if seq <= self._last_read_sent:
            return
        if not self.is_connected:
            return
        self._last_read_sent = seq
        msg = RelayMessage(
            type="read",
            room_id=self._room_id,
            sender_id=self._participant_id,
            sender_name=self._participant_name,
            sender_type=self._participant_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            read_up_to_seq=seq,
        )
        async with self._send_lock:
            assert self._ws is not None
            await self._ws.send(msg.to_json())

    async def send_edit(
        self, target_message_id: str, new_content: str
    ) -> None:
        """Send an edit message targeting a previously sent message."""
        if not self.is_connected:
            raise RuntimeError("RelayClient is not connected")
        wire_content = encrypt_content(new_content, self._room_key) if self._room_key else new_content
        msg = RelayMessage(
            type="edit",
            room_id=self._room_id,
            sender_id=self._participant_id,
            sender_name=self._participant_name,
            sender_type=self._participant_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            content=wire_content,
            target_message_id=target_message_id,
            message_id=str(uuid.uuid4()),
        )
        async with self._send_lock:
            assert self._ws is not None
            await self._ws.send(msg.to_json())

    async def send_delete(self, target_message_id: str) -> None:
        """Send a delete message targeting a previously sent message."""
        if not self.is_connected:
            raise RuntimeError("RelayClient is not connected")
        msg = RelayMessage(
            type="delete",
            room_id=self._room_id,
            sender_id=self._participant_id,
            sender_name=self._participant_name,
            sender_type=self._participant_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            target_message_id=target_message_id,
            message_id=str(uuid.uuid4()),
        )
        async with self._send_lock:
            assert self._ws is not None
            await self._ws.send(msg.to_json())

    async def receive_messages(self) -> AsyncIterator[RelayMessage]:
        """Async generator yielding messages as they arrive.

        Stops cleanly when ``disconnect()`` is called.
        """
        while self._running or not self._recv_queue.empty():
            try:
                msg = await asyncio.wait_for(self._recv_queue.get(), timeout=1.0)
                yield msg
            except asyncio.TimeoutError:
                continue

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set() and self._ws is not None

    @property
    def participants(self) -> list[dict[str, Any]]:
        return list(self._participants)

    # ------------------------------------------------------------------ #
    # Internal machinery                                                   #
    # ------------------------------------------------------------------ #

    def _build_ws_url(self) -> str:
        sep = "&" if "?" in self._url else "?"
        url = (
            f"{self._url}{sep}"
            f"room_id={self._room_id}"
            f"&participant_id={self._participant_id}"
            f"&participant_name={self._participant_name}"
            f"&participant_type={self._participant_type}"
        )
        if self._token:
            url += f"&token={self._token}"
        return url

    async def _run(self) -> None:
        """Outer reconnect loop with exponential backoff."""
        import websockets.exceptions

        attempt = 0
        while self._running:
            ws_url = self._build_ws_url()
            try:
                async with connect(ws_url) as ws:
                    self._ws = ws
                    self._connected.set()
                    self._disconnected.clear()
                    attempt = 0
                    self._reconnect_attempt = 0
                    logger.info("RelayClient connected to %s room=%s", ws_url, self._room_id)
                    if self._status_callback:
                        try:
                            self._status_callback("connected", 0)
                        except Exception:
                            pass

                    # Request missed messages since last known seq
                    await self._send_sync_request(ws)

                    await asyncio.gather(
                        self._recv_loop(ws),
                        self._heartbeat_loop(ws),
                        return_exceptions=True,
                    )
            except (websockets.exceptions.ConnectionClosed, OSError) as exc:
                logger.warning("RelayClient connection lost: %s", exc)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("RelayClient unexpected error: %s", exc)
            finally:
                self._ws = None
                self._connected.clear()
                self._disconnected.set()

            if not self._running:
                break

            backoff = min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_MAX)
            attempt += 1
            self._reconnect_attempt = attempt
            logger.info("RelayClient reconnecting in %.1fs (attempt %d)", backoff, attempt)
            if self._status_callback:
                try:
                    self._status_callback("reconnecting", attempt)
                except Exception:
                    pass
            await asyncio.sleep(backoff)

    async def _send_sync_request(self, ws: Any) -> None:
        """Ask the server for messages we missed since _last_seq."""
        req = RelayMessage(
            type="sync_request",
            room_id=self._room_id,
            sender_id=self._participant_id,
            sender_name=self._participant_name,
            sender_type=self._participant_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            seq=self._last_seq,  # "give me everything after this"
        )
        await ws.send(req.to_json())

    async def _recv_loop(self, ws: Any) -> None:
        """Receive messages from the server and push them onto the queue."""
        import websockets.exceptions

        async for raw in ws:
            try:
                msg = RelayMessage.from_json(raw)
            except Exception as exc:
                logger.warning("RelayClient could not parse message: %s", exc)
                continue

            # Keep participant list up to date
            if msg.type in ("join", "leave", "presence") and msg.participants is not None:
                self._participants = msg.participants

            # Decrypt content if we have a room key
            if self._room_key and msg.content and is_encrypted(msg.content):
                try:
                    msg.content = decrypt_content(msg.content, self._room_key)
                except Exception:
                    logger.warning("Failed to decrypt message %s", msg.message_id)

            # Track highest seq we've seen
            if msg.seq and msg.seq > self._last_seq:
                self._last_seq = msg.seq

            # Track message IDs for dedup (sync_response replay)
            if msg.message_id:
                self._seen_message_ids.add(msg.message_id)

            await self._recv_queue.put(msg)

    async def _heartbeat_loop(self, ws: Any) -> None:
        """Send a heartbeat every ``_HEARTBEAT_INTERVAL`` seconds."""
        import websockets.exceptions

        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            hb = RelayMessage(
                type="heartbeat",
                room_id=self._room_id,
                sender_id=self._participant_id,
                sender_name=self._participant_name,
                sender_type=self._participant_type,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            try:
                await ws.send(hb.to_json())
            except websockets.exceptions.ConnectionClosed:
                return
