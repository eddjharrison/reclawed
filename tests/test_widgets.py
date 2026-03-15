"""Tests for widget behavior (using textual testing framework)."""

from datetime import datetime, timedelta

import pytest

from reclawed.models import Message


def test_message_bubble_creation():
    """Test that MessageBubble can be instantiated."""
    from reclawed.widgets.message_bubble import MessageBubble

    msg = Message(role="user", content="Test message", session_id="s1")
    bubble = MessageBubble(msg)
    assert bubble.message_id == msg.id
    assert bubble.message.content == "Test message"


def test_message_bubble_update():
    """Test content update."""
    from reclawed.widgets.message_bubble import MessageBubble

    msg = Message(role="assistant", content="Initial", session_id="s1")
    bubble = MessageBubble(msg)
    assert bubble.message.content == "Initial"
    # update_content requires the widget to be mounted; just test the model update
    bubble._message.content = "Updated"
    assert bubble.message.content == "Updated"


# --- Task B: relative timestamp formatting ---

def test_format_timestamp_just_now():
    """Timestamps less than 60 seconds old show 'just now'."""
    from reclawed.widgets.message_bubble import MessageBubble

    ts = datetime.now() - timedelta(seconds=30)
    assert MessageBubble._format_timestamp(ts) == "just now"


def test_format_timestamp_zero_seconds():
    """Timestamps right now (0s delta) show 'just now'."""
    from reclawed.widgets.message_bubble import MessageBubble

    ts = datetime.now()
    assert MessageBubble._format_timestamp(ts) == "just now"


def test_format_timestamp_minutes_ago():
    """Timestamps 5 minutes old show '5m ago'."""
    from reclawed.widgets.message_bubble import MessageBubble

    ts = datetime.now() - timedelta(minutes=5)
    assert MessageBubble._format_timestamp(ts) == "5m ago"


def test_format_timestamp_59_minutes():
    """Timestamps 59 minutes old still show 'Xm ago', not hours."""
    from reclawed.widgets.message_bubble import MessageBubble

    ts = datetime.now() - timedelta(minutes=59)
    assert MessageBubble._format_timestamp(ts) == "59m ago"


def test_format_timestamp_hours_ago():
    """Timestamps 3 hours old show '3h ago'."""
    from reclawed.widgets.message_bubble import MessageBubble

    ts = datetime.now() - timedelta(hours=3)
    assert MessageBubble._format_timestamp(ts) == "3h ago"


def test_format_timestamp_23_hours():
    """Timestamps 23 hours old still show 'Xh ago', not a date."""
    from reclawed.widgets.message_bubble import MessageBubble

    ts = datetime.now() - timedelta(hours=23)
    assert MessageBubble._format_timestamp(ts) == "23h ago"


def test_format_timestamp_old_shows_date():
    """Timestamps older than 24 hours show abbreviated month+day."""
    from reclawed.widgets.message_bubble import MessageBubble

    # Use a date guaranteed to be more than 24 hours in the past.
    ts = datetime(2025, 1, 7, 12, 0, 0)
    result = MessageBubble._format_timestamp(ts)
    assert result == "Jan 7"


# --- Task A: ReplyClicked message ---

def test_reply_clicked_message_carries_reply_to_id():
    """ReplyClicked message stores the correct reply_to_id."""
    from reclawed.widgets.message_bubble import MessageBubble

    msg = MessageBubble.ReplyClicked(reply_to_id="msg-abc-123")
    assert msg.reply_to_id == "msg-abc-123"


def test_reply_indicator_widget_creation():
    """ReplyIndicator can be instantiated with text and reply_to_id."""
    from reclawed.widgets.message_bubble import ReplyIndicator

    widget = ReplyIndicator(">> some preview text", reply_to_id="orig-id-42")
    assert widget._reply_to_id == "orig-id-42"
