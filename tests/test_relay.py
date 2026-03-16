"""Tests for the Re:Clawed relay protocol and server/client integration."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest

from reclawed.relay.protocol import RelayMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_msg(**kwargs) -> RelayMessage:
    defaults = dict(
        type="message",
        room_id="room-1",
        sender_id="user-1",
        sender_name="Alice",
        sender_type="human",
        timestamp=datetime.now(timezone.utc).isoformat(),
        content="Hello",
        message_id=str(uuid.uuid4()),
    )
    defaults.update(kwargs)
    return RelayMessage(**defaults)


async def _next_msg(
    client,
    *,
    type_filter: str | None = None,
    timeout: float = 3.0,
) -> RelayMessage:
    """Pull the next message from a client's queue, optionally filtering by type."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError(f"No matching message within {timeout}s")
        msg = await asyncio.wait_for(client._recv_queue.get(), timeout=remaining)
        if type_filter is None or msg.type == type_filter:
            return msg


# ---------------------------------------------------------------------------
# Protocol unit tests
# ---------------------------------------------------------------------------

class TestRelayMessageSerialization:
    def test_round_trip_basic(self):
        msg = _make_msg()
        restored = RelayMessage.from_json(msg.to_json())
        assert restored.type == msg.type
        assert restored.room_id == msg.room_id
        assert restored.sender_id == msg.sender_id
        assert restored.content == msg.content
        assert restored.message_id == msg.message_id

    def test_round_trip_optional_fields(self):
        msg = _make_msg(reply_to_seq=5, seq=10)
        restored = RelayMessage.from_json(msg.to_json())
        assert restored.reply_to_seq == 5
        assert restored.seq == 10

    def test_none_fields_omitted_from_wire(self):
        msg = _make_msg(reply_to_seq=None, content="Hi")
        raw = json.loads(msg.to_json())
        # reply_to_seq should be absent when None
        assert "reply_to_seq" not in raw

    def test_seq_always_present(self):
        msg = _make_msg()
        raw = json.loads(msg.to_json())
        assert "seq" in raw

    def test_message_id_always_present(self):
        msg = _make_msg(message_id="")
        raw = json.loads(msg.to_json())
        assert "message_id" in raw

    def test_unknown_keys_ignored_on_deserialise(self):
        """Future server fields must not break old clients."""
        msg = _make_msg()
        raw = json.loads(msg.to_json())
        raw["future_field"] = "some-value"
        restored = RelayMessage.from_json(json.dumps(raw))
        assert restored.type == msg.type

    def test_participants_in_presence_message(self):
        participants = [
            {"id": "u1", "name": "Alice", "type": "human"},
            {"id": "u2", "name": "Bob", "type": "human"},
        ]
        msg = _make_msg(type="presence", participants=participants, content=None)
        restored = RelayMessage.from_json(msg.to_json())
        assert restored.participants == participants

    def test_error_message(self):
        msg = RelayMessage(
            type="error",
            room_id="room-1",
            sender_id="server",
            sender_name="server",
            sender_type="human",
            timestamp=datetime.now(timezone.utc).isoformat(),
            error="Something went wrong",
        )
        restored = RelayMessage.from_json(msg.to_json())
        assert restored.error == "Something went wrong"

    def test_from_json_bytes(self):
        msg = _make_msg()
        restored = RelayMessage.from_json(msg.to_json().encode())
        assert restored.sender_name == msg.sender_name

    def test_target_message_id_round_trip(self):
        """target_message_id field survives serialization."""
        msg = _make_msg(type="edit", target_message_id="msg-target-123", content="new content")
        restored = RelayMessage.from_json(msg.to_json())
        assert restored.target_message_id == "msg-target-123"
        assert restored.type == "edit"

    def test_read_up_to_seq_round_trip(self):
        """read_up_to_seq field survives serialization."""
        msg = _make_msg(type="read", read_up_to_seq=42)
        restored = RelayMessage.from_json(msg.to_json())
        assert restored.read_up_to_seq == 42

    def test_typing_message(self):
        """Typing messages serialize without content."""
        msg = _make_msg(type="typing", content=None)
        restored = RelayMessage.from_json(msg.to_json())
        assert restored.type == "typing"
        assert restored.content is None

    def test_delete_message_with_target(self):
        """Delete messages carry target_message_id."""
        msg = _make_msg(type="delete", target_message_id="msg-to-delete", content=None)
        restored = RelayMessage.from_json(msg.to_json())
        assert restored.type == "delete"
        assert restored.target_message_id == "msg-to-delete"


# ---------------------------------------------------------------------------
# Integration tests — real server/client over loopback
# ---------------------------------------------------------------------------

@pytest.fixture()
async def relay_server():
    """Start a relay server on a random free port; yield (host, port); stop it."""
    import functools
    import socket

    from websockets.asyncio.server import serve

    from reclawed.relay import server as srv

    # Obtain a free port
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    # Fresh per-test state (module-level dicts)
    srv._rooms.clear()
    srv._room_seqs.clear()

    handler = functools.partial(srv._handler, shared_token=None)
    server_instance = await serve(handler, "127.0.0.1", port)
    yield "127.0.0.1", port
    server_instance.close()
    await server_instance.wait_closed()


@pytest.mark.asyncio
async def test_two_clients_exchange_messages(relay_server):
    """Alice sends a message; Bob receives it."""
    from reclawed.relay.client import RelayClient

    host, port = relay_server
    url = f"ws://{host}:{port}"
    room = "integration-room-1"

    alice = RelayClient(url, room, "alice-id", "Alice")
    bob = RelayClient(url, room, "bob-id", "Bob")

    await alice.connect()
    await bob.connect()

    # Let presence messages drain
    await asyncio.sleep(0.1)

    await alice.send_message("Hey Bob!")

    # Collect messages from Bob until we find the chat message
    received = await _next_msg(bob, type_filter="message")

    assert received.content == "Hey Bob!"
    assert received.sender_id == "alice-id"
    assert received.seq > 0  # server assigned a seq

    await alice.disconnect()
    await bob.disconnect()


@pytest.mark.asyncio
async def test_server_assigns_monotonic_seq(relay_server):
    """Multiple messages should get strictly increasing seq numbers."""
    from reclawed.relay.client import RelayClient

    host, port = relay_server
    url = f"ws://{host}:{port}"
    room = "integration-room-2"

    alice = RelayClient(url, room, "alice-id", "Alice")
    await alice.connect()
    # Drain the sync_response and join presence messages
    await asyncio.sleep(0.1)

    await alice.send_message("First")
    await alice.send_message("Second")
    await alice.send_message("Third")

    chat_msgs: list[RelayMessage] = []
    while len(chat_msgs) < 3:
        msg = await _next_msg(alice, type_filter="message")
        chat_msgs.append(msg)

    seqs = [m.seq for m in chat_msgs]
    assert seqs == sorted(seqs), f"Seqs not monotonic: {seqs}"
    assert len(set(seqs)) == 3, f"Duplicate seqs: {seqs}"

    await alice.disconnect()


@pytest.mark.asyncio
async def test_presence_on_join(relay_server):
    """Joining client receives a presence message listing room members."""
    from reclawed.relay.client import RelayClient

    host, port = relay_server
    url = f"ws://{host}:{port}"
    room = "integration-room-3"

    alice = RelayClient(url, room, "alice-id", "Alice")
    await alice.connect()

    presence = await _next_msg(alice, type_filter="join")

    assert presence.participants is not None
    ids = [p["id"] for p in presence.participants]
    assert "alice-id" in ids

    await alice.disconnect()


@pytest.mark.asyncio
async def test_encrypted_message_exchange(relay_server):
    """Two clients with the same room key can exchange encrypted messages."""
    from reclawed.crypto import derive_room_key
    from reclawed.relay.client import RelayClient

    host, port = relay_server
    url = f"ws://{host}:{port}"
    room = "encrypted-room"
    passphrase = "test-passphrase-abc123"
    room_key = derive_room_key(passphrase, room)

    alice = RelayClient(url, room, "alice-id", "Alice", room_key=room_key)
    bob = RelayClient(url, room, "bob-id", "Bob", room_key=room_key)

    await alice.connect()
    await bob.connect()
    await asyncio.sleep(0.1)

    await alice.send_message("Secret message!")

    received = await _next_msg(bob, type_filter="message")
    # Bob should see the decrypted plaintext
    assert received.content == "Secret message!"

    await alice.disconnect()
    await bob.disconnect()


@pytest.mark.asyncio
async def test_encrypted_edit_exchange(relay_server):
    """Edit messages are encrypted and decrypted correctly."""
    from reclawed.crypto import derive_room_key
    from reclawed.relay.client import RelayClient

    host, port = relay_server
    url = f"ws://{host}:{port}"
    room = "encrypted-edit-room"
    room_key = derive_room_key("passphrase", room)

    alice = RelayClient(url, room, "alice-id", "Alice", room_key=room_key)
    bob = RelayClient(url, room, "bob-id", "Bob", room_key=room_key)

    await alice.connect()
    await bob.connect()
    await asyncio.sleep(0.1)

    await alice.send_edit("msg-123", "Updated content")

    received = await _next_msg(bob, type_filter="edit")
    assert received.content == "Updated content"
    assert received.target_message_id == "msg-123"

    await alice.disconnect()
    await bob.disconnect()


@pytest.mark.asyncio
async def test_no_key_receives_ciphertext(relay_server):
    """A client without a room key sees the raw encrypted envelope."""
    from reclawed.crypto import derive_room_key, is_encrypted
    from reclawed.relay.client import RelayClient

    host, port = relay_server
    url = f"ws://{host}:{port}"
    room = "mixed-encryption-room"
    room_key = derive_room_key("secret", room)

    alice = RelayClient(url, room, "alice-id", "Alice", room_key=room_key)
    bob = RelayClient(url, room, "bob-id", "Bob")  # no key

    await alice.connect()
    await bob.connect()
    await asyncio.sleep(0.1)

    await alice.send_message("Encrypted hello")

    received = await _next_msg(bob, type_filter="message")
    # Bob has no key — should see the encrypted envelope
    assert is_encrypted(received.content)
    assert received.content != "Encrypted hello"

    await alice.disconnect()
    await bob.disconnect()


@pytest.mark.asyncio
async def test_auth_token_rejected(relay_server):
    """A connection with a wrong token should be refused."""
    import functools
    import socket

    import websockets.exceptions
    from websockets.asyncio.client import connect
    from websockets.asyncio.server import serve

    from reclawed.relay import server as srv

    # Start a second server with a required token
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        auth_port = s.getsockname()[1]

    handler = functools.partial(srv._handler, shared_token="correct-token")
    auth_server = await serve(handler, "127.0.0.1", auth_port)

    url = (
        f"ws://127.0.0.1:{auth_port}"
        "?room_id=r&participant_id=u&participant_name=X&token=wrong-token"
    )
    with pytest.raises((websockets.exceptions.ConnectionClosed, OSError, Exception)):
        async with connect(url) as ws:
            # Server closes the connection; iterating will raise
            async for _ in ws:
                pass

    auth_server.close()
    await auth_server.wait_closed()
