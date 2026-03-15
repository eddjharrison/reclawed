"""Tests for SQLite store."""

from reclawed.models import Message, Session
from reclawed.store import Store


def test_create_and_get_session(store: Store):
    s = Session(name="My Chat")
    store.create_session(s)
    fetched = store.get_session(s.id)
    assert fetched is not None
    assert fetched.name == "My Chat"


def test_list_sessions(store: Store):
    store.create_session(Session(name="A"))
    store.create_session(Session(name="B"))
    sessions = store.list_sessions()
    assert len(sessions) == 2


def test_add_and_get_message(store: Store, session: Session):
    msg = Message(role="user", content="Hello", session_id=session.id)
    store.add_message(msg)
    fetched = store.get_message(msg.id)
    assert fetched is not None
    assert fetched.content == "Hello"
    assert fetched.seq == 1


def test_auto_increment_seq(store: Store, session: Session):
    m1 = Message(role="user", content="First", session_id=session.id)
    m2 = Message(role="assistant", content="Second", session_id=session.id)
    store.add_message(m1)
    store.add_message(m2)
    assert m1.seq == 1
    assert m2.seq == 2


def test_session_messages(store: Store, session: Session):
    store.add_message(Message(role="user", content="A", session_id=session.id))
    store.add_message(Message(role="assistant", content="B", session_id=session.id))
    msgs = store.get_session_messages(session.id)
    assert len(msgs) == 2
    assert msgs[0].content == "A"
    assert msgs[1].content == "B"


def test_bookmark(store: Store, session: Session):
    msg = Message(role="user", content="Important", session_id=session.id)
    store.add_message(msg)
    msg.bookmarked = True
    store.update_message(msg)
    bookmarked = store.get_bookmarked_messages(session.id)
    assert len(bookmarked) == 1
    assert bookmarked[0].id == msg.id


def test_search(store: Store, session: Session):
    store.add_message(Message(role="user", content="Hello world", session_id=session.id))
    store.add_message(Message(role="assistant", content="Goodbye", session_id=session.id))
    results = store.search_messages("Hello", session.id)
    assert len(results) == 1
    assert results[0].content == "Hello world"


def test_reply_chain(store: Store, session: Session):
    m1 = Message(role="user", content="Root", session_id=session.id)
    store.add_message(m1)
    m2 = Message(role="assistant", content="Reply1", session_id=session.id, reply_to_id=m1.id)
    store.add_message(m2)
    m3 = Message(role="user", content="Reply2", session_id=session.id, reply_to_id=m2.id)
    store.add_message(m3)
    chain = store.get_reply_chain(m3.id)
    assert len(chain) == 3
    assert chain[0].content == "Root"
    assert chain[2].content == "Reply2"


def test_delete_session(store: Store, session: Session):
    store.add_message(Message(role="user", content="X", session_id=session.id))
    store.delete_session(session.id)
    assert store.get_session(session.id) is None
    assert store.get_session_messages(session.id) == []


def test_update_session(store: Store, session: Session):
    session.name = "Renamed"
    store.update_session(session)
    fetched = store.get_session(session.id)
    assert fetched.name == "Renamed"


# --- New sidebar data-layer tests ---

def test_get_last_message_empty(store: Store, session: Session):
    """Returns None when the session has no messages."""
    assert store.get_last_message(session.id) is None


def test_get_last_message_returns_most_recent(store: Store, session: Session):
    """Returns the message with the highest seq value."""
    m1 = Message(role="user", content="First", session_id=session.id)
    m2 = Message(role="assistant", content="Second", session_id=session.id)
    m3 = Message(role="user", content="Third", session_id=session.id)
    for m in (m1, m2, m3):
        store.add_message(m)
    last = store.get_last_message(session.id)
    assert last is not None
    assert last.content == "Third"
    assert last.seq == 3


def test_list_sessions_excludes_archived_by_default(store: Store):
    """list_sessions() hides archived sessions unless include_archived=True."""
    active = Session(name="Active")
    archived = Session(name="Archived", archived=True)
    store.create_session(active)
    store.create_session(archived)

    visible = store.list_sessions()
    assert len(visible) == 1
    assert visible[0].name == "Active"

    all_sessions = store.list_sessions(include_archived=True)
    assert len(all_sessions) == 2


def test_list_sessions_include_archived_flag(store: Store):
    """Archived sessions appear when include_archived=True."""
    s1 = Session(name="A", archived=True)
    s2 = Session(name="B", archived=True)
    store.create_session(s1)
    store.create_session(s2)

    assert store.list_sessions() == []
    assert len(store.list_sessions(include_archived=True)) == 2


def test_mark_session_read(store: Store, session: Session):
    """mark_session_read resets unread_count to 0."""
    store.increment_unread(session.id)
    store.increment_unread(session.id)
    store.increment_unread(session.id)

    before = store.get_session(session.id)
    assert before.unread_count == 3

    store.mark_session_read(session.id)
    after = store.get_session(session.id)
    assert after.unread_count == 0


def test_increment_unread(store: Store, session: Session):
    """increment_unread increments by exactly 1 each call."""
    assert store.get_session(session.id).unread_count == 0

    store.increment_unread(session.id)
    assert store.get_session(session.id).unread_count == 1

    store.increment_unread(session.id)
    store.increment_unread(session.id)
    assert store.get_session(session.id).unread_count == 3


def test_new_session_defaults(store: Store):
    """New sessions have expected default values for the sidebar fields."""
    s = Session(name="Defaults")
    store.create_session(s)
    fetched = store.get_session(s.id)
    assert fetched.muted is False
    assert fetched.archived is False
    assert fetched.unread_count == 0


def test_update_session_persists_sidebar_fields(store: Store, session: Session):
    """update_session correctly writes muted, archived, and unread_count."""
    session.muted = True
    session.archived = True
    session.unread_count = 7
    store.update_session(session)

    fetched = store.get_session(session.id)
    assert fetched.muted is True
    assert fetched.archived is True
    assert fetched.unread_count == 7
