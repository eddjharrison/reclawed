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


# --- Message editing tests ---

def test_update_message_with_edited_at(store: Store, session: Session):
    """edited_at is persisted and returned correctly."""
    from datetime import datetime, timezone
    msg = Message(role="user", content="Original", session_id=session.id)
    store.add_message(msg)

    now = datetime.now(timezone.utc)
    msg.content = "Edited content"
    msg.edited_at = now
    store.update_message(msg)

    fetched = store.get_message(msg.id)
    assert fetched.content == "Edited content"
    assert fetched.edited_at is not None
    assert fetched.edited_at.year == now.year


def test_edited_at_none_by_default(store: Store, session: Session):
    """New messages have edited_at=None."""
    msg = Message(role="user", content="Fresh", session_id=session.id)
    store.add_message(msg)
    fetched = store.get_message(msg.id)
    assert fetched.edited_at is None


# --- Soft delete tests ---

def test_soft_delete_message(store: Store, session: Session):
    """soft_delete_message sets the deleted flag."""
    msg = Message(role="user", content="Delete me", session_id=session.id)
    store.add_message(msg)
    store.soft_delete_message(msg.id)
    fetched = store.get_message(msg.id)
    assert fetched.deleted is True


def test_soft_delete_still_in_session_messages(store: Store, session: Session):
    """Soft-deleted messages remain in get_session_messages (timeline)."""
    msg = Message(role="user", content="Will delete", session_id=session.id)
    store.add_message(msg)
    store.soft_delete_message(msg.id)
    msgs = store.get_session_messages(session.id)
    assert len(msgs) == 1
    assert msgs[0].deleted is True


def test_search_excludes_deleted(store: Store, session: Session):
    """search_messages skips deleted messages."""
    m1 = Message(role="user", content="Keep me visible", session_id=session.id)
    m2 = Message(role="user", content="Keep this hidden", session_id=session.id)
    store.add_message(m1)
    store.add_message(m2)
    store.soft_delete_message(m2.id)
    results = store.search_messages("Keep", session.id)
    assert len(results) == 1
    assert results[0].content == "Keep me visible"


def test_export_excludes_deleted(store: Store, session: Session):
    """export_session_markdown skips deleted messages."""
    m1 = Message(role="user", content="Visible message", session_id=session.id)
    m2 = Message(role="user", content="Deleted message", session_id=session.id)
    store.add_message(m1)
    store.add_message(m2)
    store.soft_delete_message(m2.id)
    md = store.export_session_markdown(session.id)
    assert "Visible message" in md
    assert "Deleted message" not in md


def test_deleted_false_by_default(store: Store, session: Session):
    """New messages have deleted=False."""
    msg = Message(role="user", content="Normal", session_id=session.id)
    store.add_message(msg)
    fetched = store.get_message(msg.id)
    assert fetched.deleted is False


# --- Local encryption tests ---


def test_encrypted_store_round_trip():
    """Messages are encrypted at rest and decrypted on read."""
    import os
    key = os.urandom(32)
    s = Store(":memory:", local_key=key)
    session = Session(name="Encrypted Session")
    s.create_session(session)

    msg = Message(role="user", content="Secret message", session_id=session.id)
    s.add_message(msg)

    fetched = s.get_message(msg.id)
    assert fetched.content == "Secret message"
    s.close()


def test_encrypted_content_stored_as_ciphertext():
    """Raw DB content is ciphertext, not plaintext."""
    import os
    from reclawed.crypto import is_encrypted
    key = os.urandom(32)
    s = Store(":memory:", local_key=key)
    session = Session(name="Test")
    s.create_session(session)

    msg = Message(role="user", content="Plaintext here", session_id=session.id)
    s.add_message(msg)

    # Read raw from DB bypassing decryption
    row = s._conn.execute("SELECT content, encrypted FROM messages WHERE id = ?", (msg.id,)).fetchone()
    assert row["encrypted"] == 1
    assert is_encrypted(row["content"])
    assert row["content"] != "Plaintext here"
    s.close()


def test_encrypted_update_message():
    """update_message re-encrypts content."""
    import os
    from reclawed.crypto import is_encrypted
    key = os.urandom(32)
    s = Store(":memory:", local_key=key)
    session = Session(name="Test")
    s.create_session(session)

    msg = Message(role="user", content="Original", session_id=session.id)
    s.add_message(msg)

    msg.content = "Updated"
    s.update_message(msg)

    fetched = s.get_message(msg.id)
    assert fetched.content == "Updated"

    # Raw DB is encrypted
    row = s._conn.execute("SELECT content FROM messages WHERE id = ?", (msg.id,)).fetchone()
    assert is_encrypted(row["content"])
    s.close()


def test_encrypted_search():
    """search_messages works with encrypted content via Python filtering."""
    import os
    key = os.urandom(32)
    s = Store(":memory:", local_key=key)
    session = Session(name="Test")
    s.create_session(session)

    s.add_message(Message(role="user", content="The quick brown fox", session_id=session.id))
    s.add_message(Message(role="user", content="Lazy dog", session_id=session.id))

    results = s.search_messages("quick")
    assert len(results) == 1
    assert "quick" in results[0].content

    results = s.search_messages("dog")
    assert len(results) == 1
    assert "dog" in results[0].content
    s.close()


def test_unencrypted_messages_still_readable():
    """Old plaintext messages (encrypted=0) are readable even with a local key."""
    import os
    key = os.urandom(32)
    s = Store(":memory:", local_key=key)
    session = Session(name="Test")
    s.create_session(session)

    # Simulate a pre-encryption message by inserting directly
    s._conn.execute(
        "INSERT INTO messages (id, seq, role, content, timestamp, session_id, encrypted) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("old-msg", 1, "user", "Legacy plaintext", "2024-01-01T00:00:00+00:00",
         session.id, 0),
    )
    s._conn.commit()

    fetched = s.get_message("old-msg")
    assert fetched.content == "Legacy plaintext"
    s.close()


def test_session_encryption_passphrase():
    """Session encryption_passphrase is persisted and loaded."""
    s = Store(":memory:")
    session = Session(name="Group", is_group=True, encryption_passphrase="abc123")
    s.create_session(session)

    fetched = s.get_session(session.id)
    assert fetched.encryption_passphrase == "abc123"

    session.encryption_passphrase = "updated"
    s.update_session(session)
    fetched = s.get_session(session.id)
    assert fetched.encryption_passphrase == "updated"
    s.close()
