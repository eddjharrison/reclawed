"""Tests for data models."""

from reclawed.models import Message, Session


def test_message_defaults():
    msg = Message(role="user", content="Hello", session_id="s1")
    assert msg.id  # UUID generated
    assert msg.seq == 0
    assert msg.role == "user"
    assert msg.content == "Hello"
    assert msg.reply_to_id is None
    assert msg.bookmarked is False


def test_session_defaults():
    s = Session()
    assert s.id
    assert s.name == "New Chat"
    assert s.total_cost_usd == 0.0
    assert s.message_count == 0


def test_message_with_reply():
    msg = Message(role="assistant", content="Reply", session_id="s1", reply_to_id="msg-1")
    assert msg.reply_to_id == "msg-1"
