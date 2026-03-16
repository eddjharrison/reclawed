"""Tests for data models and related screen helpers."""

from reclawed.models import Message, Session
from reclawed.screens.chat import ChatScreen


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


# ---------------------------------------------------------------------------
# ChatScreen._derive_session_name
# ---------------------------------------------------------------------------

def test_derive_session_name_short_prompt():
    """Prompts under the limit are returned as-is (stripped)."""
    assert ChatScreen._derive_session_name("Hello there") == "Hello there"


def test_derive_session_name_strips_whitespace():
    assert ChatScreen._derive_session_name("  hi  ") == "hi"


def test_derive_session_name_truncates_at_word_boundary():
    # 41 chars — should truncate before the last word and add "..."
    prompt = "Tell me about the history of the Roman Empire"
    result = ChatScreen._derive_session_name(prompt, max_len=40)
    assert result.endswith("...")
    # The visible text (without "...") must be at most 40 chars
    assert len(result.removesuffix("...")) <= 40
    # No mid-word cuts
    assert not result.removesuffix("...").endswith(" ")


def test_derive_session_name_exact_limit():
    """A prompt exactly at the limit is returned without ellipsis."""
    prompt = "a" * 40
    assert ChatScreen._derive_session_name(prompt) == prompt


def test_derive_session_name_multiline_prompt():
    """Newlines are collapsed to spaces before truncation."""
    prompt = "First line\nSecond line"
    result = ChatScreen._derive_session_name(prompt)
    assert "\n" not in result
    assert result == "First line Second line"


def test_derive_session_name_no_space_fallback():
    """If there is no space in the truncation window, cut hard at max_len."""
    prompt = "a" * 50
    result = ChatScreen._derive_session_name(prompt, max_len=40)
    # rfind returns -1 when there's no space, so we fall back to the raw slice + "..."
    assert result == "a" * 40 + "..."


# ---------------------------------------------------------------------------
# New model fields (editing + deletion)
# ---------------------------------------------------------------------------

def test_message_edited_at_default():
    msg = Message(role="user", content="Hello", session_id="s1")
    assert msg.edited_at is None


def test_message_deleted_default():
    msg = Message(role="user", content="Hello", session_id="s1")
    assert msg.deleted is False


def test_message_with_edited_at():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    msg = Message(role="user", content="Edited", session_id="s1", edited_at=now)
    assert msg.edited_at == now


def test_message_with_deleted():
    msg = Message(role="user", content="Deleted", session_id="s1", deleted=True)
    assert msg.deleted is True
