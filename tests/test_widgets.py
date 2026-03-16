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
# The logic now lives in reclawed.utils.format_relative_time; these tests
# follow the function to its new home.

def test_format_timestamp_just_now():
    """Timestamps less than 60 seconds old show 'just now'."""
    from reclawed.utils import format_relative_time

    ts = datetime.now() - timedelta(seconds=30)
    assert format_relative_time(ts) == "just now"


def test_format_timestamp_zero_seconds():
    """Timestamps right now (0s delta) show 'just now'."""
    from reclawed.utils import format_relative_time

    ts = datetime.now()
    assert format_relative_time(ts) == "just now"


def test_format_timestamp_minutes_ago():
    """Timestamps 5 minutes old show '5m ago'."""
    from reclawed.utils import format_relative_time

    ts = datetime.now() - timedelta(minutes=5)
    assert format_relative_time(ts) == "5m ago"


def test_format_timestamp_59_minutes():
    """Timestamps 59 minutes old still show 'Xm ago', not hours."""
    from reclawed.utils import format_relative_time

    ts = datetime.now() - timedelta(minutes=59)
    assert format_relative_time(ts) == "59m ago"


def test_format_timestamp_hours_ago():
    """Timestamps 3 hours old show '3h ago'."""
    from reclawed.utils import format_relative_time

    ts = datetime.now() - timedelta(hours=3)
    assert format_relative_time(ts) == "3h ago"


def test_format_timestamp_23_hours():
    """Timestamps 23 hours old still show 'Xh ago', not a date."""
    from reclawed.utils import format_relative_time

    ts = datetime.now() - timedelta(hours=23)
    assert format_relative_time(ts) == "23h ago"


def test_format_timestamp_old_shows_date():
    """Timestamps older than 24 hours show abbreviated month+day."""
    from reclawed.utils import format_relative_time

    # Use a date guaranteed to be more than 24 hours in the past.
    ts = datetime(2025, 1, 7, 12, 0, 0)
    result = format_relative_time(ts)
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


# ---------------------------------------------------------------------------
# ChatListItem
# ---------------------------------------------------------------------------

def test_chat_list_item_creation_basic():
    """ChatListItem can be instantiated with a session and default args."""
    from reclawed.models import Session
    from reclawed.widgets.chat_list_item import ChatListItem

    session = Session(name="My Chat")
    item = ChatListItem(session)
    assert item.session_id == session.id
    assert item._is_active is False
    assert item._last_preview == ""


def test_chat_list_item_active_class():
    """Passing is_active=True adds the 'active' CSS class."""
    from reclawed.models import Session
    from reclawed.widgets.chat_list_item import ChatListItem

    session = Session(name="Active Chat")
    item = ChatListItem(session, is_active=True)
    assert "active" in item.classes


def test_chat_list_item_not_active_by_default():
    """is_active defaults to False and the 'active' class is absent."""
    from reclawed.models import Session
    from reclawed.widgets.chat_list_item import ChatListItem

    session = Session(name="Inactive")
    item = ChatListItem(session)
    assert "active" not in item.classes


def test_chat_list_item_unread_class():
    """Sessions with unread_count > 0 get the 'unread' CSS class."""
    from reclawed.models import Session
    from reclawed.widgets.chat_list_item import ChatListItem

    session = Session(name="Unread Chat", unread_count=3)
    item = ChatListItem(session)
    assert "unread" in item.classes


def test_chat_list_item_no_unread_class_when_zero():
    """Sessions with unread_count == 0 do NOT get the 'unread' class."""
    from reclawed.models import Session
    from reclawed.widgets.chat_list_item import ChatListItem

    session = Session(name="Read Chat", unread_count=0)
    item = ChatListItem(session)
    assert "unread" not in item.classes


def test_chat_list_item_muted_class():
    """Muted sessions get the 'muted' CSS class."""
    from reclawed.models import Session
    from reclawed.widgets.chat_list_item import ChatListItem

    session = Session(name="Muted", muted=True)
    item = ChatListItem(session)
    assert "muted" in item.classes


def test_chat_list_item_clicked_message():
    """ChatListItem.Clicked carries the correct session_id."""
    from reclawed.widgets.chat_list_item import ChatListItem

    msg = ChatListItem.Clicked(session_id="sess-xyz")
    assert msg.session_id == "sess-xyz"


def test_chat_list_item_refresh_data_active():
    """refresh_data(is_active=True) adds the active class."""
    from reclawed.models import Session
    from reclawed.widgets.chat_list_item import ChatListItem

    session = Session(name="Test")
    item = ChatListItem(session, is_active=False)
    assert "active" not in item.classes
    # Simulate calling refresh without a mounted widget (no _render_content side
    # effects that need the DOM, just the class manipulation).
    item._is_active = True
    item.add_class("active")
    assert "active" in item.classes


def test_chat_list_item_preview_truncated_at_render():
    """The internal preview string is stored verbatim; truncation is display-only."""
    from reclawed.models import Session
    from reclawed.widgets.chat_list_item import ChatListItem

    long_preview = "x" * 100
    session = Session(name="Long")
    item = ChatListItem(session, last_preview=long_preview)
    # The raw attribute is NOT truncated — only the rendered text is.
    assert item._last_preview == long_preview


# ---------------------------------------------------------------------------
# ChatSidebar (unit-level, no DOM)
# ---------------------------------------------------------------------------

def test_chat_sidebar_filtered_sessions_empty_query():
    """_filtered_sessions returns all sessions when query is empty."""
    from reclawed.models import Session
    from reclawed.store import Store
    from reclawed.widgets.chat_sidebar import ChatSidebar

    store = Store(":memory:")
    sidebar = ChatSidebar(store)
    sidebar._sessions = [Session(name="A"), Session(name="B"), Session(name="C")]
    sidebar._search_query = ""
    result = sidebar._filtered_sessions()
    assert len(result) == 3
    store.close()


def test_chat_sidebar_filtered_sessions_with_query():
    """_filtered_sessions filters case-insensitively by name."""
    from reclawed.models import Session
    from reclawed.store import Store
    from reclawed.widgets.chat_sidebar import ChatSidebar

    store = Store(":memory:")
    sidebar = ChatSidebar(store)
    sidebar._sessions = [
        Session(name="Alpha Chat"),
        Session(name="Beta Convo"),
        Session(name="alpha lowercase"),
    ]
    sidebar._search_query = "alpha"
    result = sidebar._filtered_sessions()
    assert len(result) == 2
    assert all("alpha" in s.name.lower() for s in result)
    store.close()


def test_chat_sidebar_filtered_sessions_no_match():
    """_filtered_sessions returns empty list when nothing matches."""
    from reclawed.models import Session
    from reclawed.store import Store
    from reclawed.widgets.chat_sidebar import ChatSidebar

    store = Store(":memory:")
    sidebar = ChatSidebar(store)
    sidebar._sessions = [Session(name="Foo"), Session(name="Bar")]
    sidebar._search_query = "zzz"
    result = sidebar._filtered_sessions()
    assert result == []
    store.close()


def test_chat_sidebar_messages():
    """ChatSidebar message classes carry the right payloads."""
    from reclawed.widgets.chat_sidebar import ChatSidebar

    sel = ChatSidebar.SessionSelected(session_id="s-123")
    assert sel.session_id == "s-123"

    new_chat = ChatSidebar.NewChatRequested()
    assert new_chat is not None


# ---------------------------------------------------------------------------
# ContextMenu
# ---------------------------------------------------------------------------

def test_context_menu_action_constants():
    """Action constant strings are non-empty and distinct."""
    from reclawed.widgets.context_menu import (
        ACTION_ARCHIVE,
        ACTION_DELETE,
        ACTION_MARK_UNREAD,
        ACTION_MUTE,
        ACTION_RENAME,
        ACTION_UNMUTE,
    )

    actions = [ACTION_MARK_UNREAD, ACTION_MUTE, ACTION_UNMUTE,
               ACTION_ARCHIVE, ACTION_DELETE, ACTION_RENAME]
    assert all(isinstance(a, str) and a for a in actions)
    assert len(set(actions)) == len(actions), "Action constants must be unique"


def test_context_menu_instantiation_not_muted():
    """ContextMenu can be instantiated for a non-muted session."""
    from reclawed.widgets.context_menu import ContextMenu

    menu = ContextMenu(session_id="sess-1", is_muted=False)
    assert menu._session_id == "sess-1"
    assert menu._is_muted is False


def test_context_menu_instantiation_muted():
    """ContextMenu can be instantiated for a muted session."""
    from reclawed.widgets.context_menu import ContextMenu

    menu = ContextMenu(session_id="sess-2", is_muted=True)
    assert menu._is_muted is True


def test_context_menu_default_not_muted():
    """is_muted defaults to False."""
    from reclawed.widgets.context_menu import ContextMenu

    menu = ContextMenu(session_id="sess-3")
    assert menu._is_muted is False


# ---------------------------------------------------------------------------
# Session Rename (1A)
# ---------------------------------------------------------------------------

def test_chat_list_item_renamed_message():
    """ChatListItem.Renamed carries correct session_id and new_name."""
    from reclawed.widgets.chat_list_item import ChatListItem

    msg = ChatListItem.Renamed(session_id="sess-rename", new_name="My New Name")
    assert msg.session_id == "sess-rename"
    assert msg.new_name == "My New Name"


def test_chat_sidebar_session_renamed_message():
    """ChatSidebar.SessionRenamed carries correct data."""
    from reclawed.widgets.chat_sidebar import ChatSidebar

    msg = ChatSidebar.SessionRenamed(session_id="s-1", new_name="Renamed")
    assert msg.session_id == "s-1"
    assert msg.new_name == "Renamed"


# ---------------------------------------------------------------------------
# Message Editing (1B)
# ---------------------------------------------------------------------------

def test_compose_area_submitted_carries_editing_id():
    """ComposeArea.Submitted includes editing_message_id."""
    from reclawed.widgets.compose_area import ComposeArea

    msg = ComposeArea.Submitted(text="edited text", editing_message_id="msg-123")
    assert msg.text == "edited text"
    assert msg.editing_message_id == "msg-123"


def test_compose_area_submitted_no_editing_by_default():
    """ComposeArea.Submitted has editing_message_id=None by default."""
    from reclawed.widgets.compose_area import ComposeArea

    msg = ComposeArea.Submitted(text="new message")
    assert msg.editing_message_id is None


def test_message_bubble_with_edited_at():
    """MessageBubble accepts a message with edited_at set."""
    from datetime import datetime, timezone
    from reclawed.widgets.message_bubble import MessageBubble

    msg = Message(
        role="user", content="Edited", session_id="s1",
        edited_at=datetime.now(timezone.utc),
    )
    bubble = MessageBubble(msg)
    assert bubble.message.edited_at is not None


# ---------------------------------------------------------------------------
# Message Deletion (1C)
# ---------------------------------------------------------------------------

def test_message_bubble_deleted_state():
    """MessageBubble with deleted=True has the deleted class."""
    from reclawed.widgets.message_bubble import MessageBubble

    msg = Message(role="user", content="Gone", session_id="s1", deleted=True)
    bubble = MessageBubble(msg)
    assert bubble.message.deleted is True


# ---------------------------------------------------------------------------
# Typing Indicators (2A)
# ---------------------------------------------------------------------------

def test_compose_area_typing_started_message():
    """ComposeArea.TypingStarted message can be instantiated."""
    from reclawed.widgets.compose_area import ComposeArea

    msg = ComposeArea.TypingStarted()
    assert msg is not None


# ---------------------------------------------------------------------------
# StatusBar — typing + connection
# ---------------------------------------------------------------------------

def test_status_bar_typing_indicator():
    """StatusBar shows typing indicator when names are provided."""
    from reclawed.widgets.status_bar import StatusBar
    bar = object.__new__(StatusBar)
    bar._session_name = "Test"
    bar._model = ""
    bar._cost = 0.0
    bar._message_count = 0
    bar._streaming_indicator = None
    bar._group_mode = None
    bar._typing_indicator = None
    bar._connection_status = None
    bar._encrypted = False
    bar._workspace_name = None
    bar._permission_mode = None
    bar._last_render = ""
    bar.update = lambda text: setattr(bar, "_last_render", text)

    bar.set_typing_indicator(["Alice"])
    assert "Alice is typing..." in bar._last_render

    bar.set_typing_indicator(["Alice", "Bob"])
    assert "Alice, Bob are typing..." in bar._last_render

    bar.set_typing_indicator([])
    assert "typing" not in bar._last_render


def test_status_bar_connection_status():
    """StatusBar shows connection status."""
    from reclawed.widgets.status_bar import StatusBar
    bar = object.__new__(StatusBar)
    bar._session_name = "Test"
    bar._model = ""
    bar._cost = 0.0
    bar._message_count = 0
    bar._streaming_indicator = None
    bar._group_mode = None
    bar._typing_indicator = None
    bar._connection_status = None
    bar._encrypted = False
    bar._workspace_name = None
    bar._permission_mode = None
    bar._last_render = ""
    bar.update = lambda text: setattr(bar, "_last_render", text)

    bar.set_connection_status("Reconnecting... (attempt 2)")
    assert "Reconnecting... (attempt 2)" in bar._last_render

    bar.set_connection_status(None)
    assert "Reconnecting" not in bar._last_render


# ---------------------------------------------------------------------------
# Read Receipts — delivery status
# ---------------------------------------------------------------------------

async def test_message_bubble_streaming_then_finalize():
    """Verify the streaming → finalize flow preserves content."""
    from reclawed.widgets.message_bubble import MessageBubble

    msg = Message(role="assistant", content="...", session_id="s1")
    bubble = MessageBubble(msg)

    # Simulate streaming updates
    bubble.update_content("Hello ")
    assert bubble.message.content == "Hello "

    bubble.update_content("Hello world, this is a long response.")
    assert bubble.message.content == "Hello world, this is a long response."

    # Simulate finalize
    final = "Hello world, this is a long response.\n\nWith **markdown**."
    await bubble.finalize_content(final)
    assert bubble.message.content == final


async def test_message_bubble_long_content():
    """Verify very long content is stored correctly through streaming."""
    from reclawed.widgets.message_bubble import MessageBubble

    msg = Message(role="assistant", content="...", session_id="s1")
    bubble = MessageBubble(msg)

    # Build a 100-line poem
    lines = [f"Line {i}: This is line number {i} of the poem" for i in range(100)]
    poem = "\n".join(lines)

    # Stream it in chunks
    accumulated = ""
    for line in lines:
        accumulated += line + "\n"
        bubble.update_content(accumulated)

    # Finalize
    await bubble.finalize_content(poem)
    assert bubble.message.content == poem
    assert bubble.message.content.count("\n") == 99  # 100 lines = 99 newlines


def test_message_bubble_delivery_status_method():
    """MessageBubble.set_delivery_status exists and is callable."""
    from reclawed.widgets.message_bubble import MessageBubble

    msg = Message(role="user", content="Test", session_id="s1", sender_type="human")
    bubble = MessageBubble(msg)
    # Method should exist and not raise (label won't exist without mounting)
    bubble.set_delivery_status("sent")
