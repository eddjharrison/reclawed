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
