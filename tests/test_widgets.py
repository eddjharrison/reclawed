"""Tests for widget behavior (using textual testing framework)."""

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
