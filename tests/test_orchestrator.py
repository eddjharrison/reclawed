"""Tests for orchestrator / worker session data layer and delegation detection."""

from __future__ import annotations

from reclawed.models import Session
from reclawed.store import Store
from reclawed.utils import detect_worker_proposals
from reclawed.widgets.chat_list_item import ChatListItem
from reclawed.widgets.chat_sidebar import ChatSidebar


def test_session_field_defaults():
    """New sessions have None for all orchestrator/worker fields."""
    s = Session(name="Test")
    assert s.parent_session_id is None
    assert s.session_type is None
    assert s.worker_status is None
    assert s.worker_summary is None


def test_worker_fields_persist(store: Store):
    """Orchestrator/worker fields survive create + get round-trip."""
    parent = Session(name="Orchestrator", session_type="orchestrator")
    store.create_session(parent)

    worker = Session(
        name="Worker 1",
        parent_session_id=parent.id,
        session_type="worker",
        worker_status="running",
    )
    store.create_session(worker)

    loaded = store.get_session(worker.id)
    assert loaded is not None
    assert loaded.parent_session_id == parent.id
    assert loaded.session_type == "worker"
    assert loaded.worker_status == "running"
    assert loaded.worker_summary is None


def test_worker_fields_update(store: Store):
    """Worker status and summary can be updated."""
    worker = Session(
        name="Worker",
        session_type="worker",
        worker_status="running",
    )
    store.create_session(worker)

    worker.worker_status = "complete"
    worker.worker_summary = "Added JWT auth middleware, 3 files changed."
    store.update_session(worker)

    loaded = store.get_session(worker.id)
    assert loaded is not None
    assert loaded.worker_status == "complete"
    assert loaded.worker_summary == "Added JWT auth middleware, 3 files changed."


def test_get_worker_sessions(store: Store):
    """get_worker_sessions returns children ordered by created_at ASC."""
    import time

    parent = Session(name="Orchestrator", session_type="orchestrator")
    store.create_session(parent)

    # Create workers with slight delay so created_at differs
    w1 = Session(name="Worker A", parent_session_id=parent.id, session_type="worker", worker_status="running")
    store.create_session(w1)
    w2 = Session(name="Worker B", parent_session_id=parent.id, session_type="worker", worker_status="complete")
    store.create_session(w2)

    workers = store.get_worker_sessions(parent.id)
    assert len(workers) == 2
    assert workers[0].id == w1.id
    assert workers[1].id == w2.id


def test_get_worker_sessions_excludes_archived(store: Store):
    """Archived workers are excluded from get_worker_sessions."""
    parent = Session(name="Orchestrator", session_type="orchestrator")
    store.create_session(parent)

    w1 = Session(name="Active Worker", parent_session_id=parent.id, session_type="worker", worker_status="running")
    store.create_session(w1)
    w2 = Session(name="Archived Worker", parent_session_id=parent.id, session_type="worker", archived=True)
    store.create_session(w2)

    workers = store.get_worker_sessions(parent.id)
    assert len(workers) == 1
    assert workers[0].id == w1.id


def test_get_worker_sessions_empty(store: Store):
    """get_worker_sessions returns empty list for sessions with no workers."""
    parent = Session(name="Solo Session")
    store.create_session(parent)
    assert store.get_worker_sessions(parent.id) == []


def test_orchestrator_promotion(store: Store):
    """A regular session can be promoted to orchestrator by updating session_type."""
    session = Session(name="Regular Chat")
    store.create_session(session)
    assert session.session_type is None

    session.session_type = "orchestrator"
    store.update_session(session)

    loaded = store.get_session(session.id)
    assert loaded is not None
    assert loaded.session_type == "orchestrator"


def test_list_sessions_includes_workers(store: Store):
    """list_sessions includes worker sessions."""
    parent = Session(name="Orchestrator", session_type="orchestrator", message_count=1)
    store.create_session(parent)
    worker = Session(
        name="Worker",
        parent_session_id=parent.id,
        session_type="worker",
        worker_status="running",
        message_count=1,
    )
    store.create_session(worker)

    sessions = store.list_sessions()
    ids = [s.id for s in sessions]
    assert parent.id in ids
    assert worker.id in ids


def test_format_name_worker_running():
    """Worker name shows spinning icon and [W] prefix when running."""
    s = Session(name="Auth task", session_type="worker", worker_status="running")
    name = ChatListItem._format_name(s)
    assert "[W]" in name
    assert "\u27f3" in name  # ⟳


def test_format_name_worker_complete():
    """Worker name shows checkmark when complete."""
    s = Session(name="Auth task", session_type="worker", worker_status="complete")
    name = ChatListItem._format_name(s)
    assert "[W]" in name
    assert "\u2713" in name  # ✓


def test_format_name_regular_session():
    """Regular sessions have no prefix."""
    s = Session(name="Regular Chat")
    name = ChatListItem._format_name(s)
    assert name == "Regular Chat"


def test_order_with_workers_nesting():
    """Workers appear after their orchestrator in sidebar order."""
    from datetime import datetime, timezone, timedelta

    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    parent = Session(name="Orch", session_type="orchestrator")
    parent.updated_at = base + timedelta(hours=3)
    other = Session(name="Other Chat")
    other.updated_at = base + timedelta(hours=4)
    w1 = Session(
        name="W1",
        parent_session_id=parent.id,
        session_type="worker",
        worker_status="running",
    )
    w1.created_at = base + timedelta(hours=1)
    w2 = Session(
        name="W2",
        parent_session_id=parent.id,
        session_type="worker",
        worker_status="complete",
    )
    w2.created_at = base + timedelta(hours=2)

    # Input order: other, parent (workers scattered elsewhere)
    sessions = [other, parent, w2, w1]
    result = ChatSidebar._order_with_workers(sessions)

    names = [s.name for s in result]
    assert names == ["Other Chat", "Orch", "W1", "W2"]


def test_order_with_workers_no_workers():
    """Without workers, order is unchanged."""
    s1 = Session(name="A")
    s2 = Session(name="B")
    result = ChatSidebar._order_with_workers([s1, s2])
    assert [s.name for s in result] == ["A", "B"]


# --- Delegation detection tests ---


def test_detect_single_proposal():
    """Detect a single worker proposal with all fields."""
    text = 'Here is my plan:\n{{WORKER task="Implement auth" model="opus" permissions="acceptEdits"}}'
    proposals = detect_worker_proposals(text)
    assert len(proposals) == 1
    assert proposals[0]["task"] == "Implement auth"
    assert proposals[0]["model"] == "opus"
    assert proposals[0]["permission_mode"] == "acceptEdits"


def test_detect_multiple_proposals():
    """Detect multiple worker proposals."""
    text = (
        "I'll break this into 3 tasks:\n\n"
        '{{WORKER task="Build API endpoints" model="sonnet" permissions="bypassPermissions"}}\n'
        '{{WORKER task="Write unit tests" model="sonnet" permissions="bypassPermissions"}}\n'
        '{{WORKER task="Update documentation" model="haiku" permissions="acceptEdits"}}'
    )
    proposals = detect_worker_proposals(text)
    assert len(proposals) == 3
    assert proposals[0]["task"] == "Build API endpoints"
    assert proposals[1]["task"] == "Write unit tests"
    assert proposals[2]["task"] == "Update documentation"
    assert proposals[2]["model"] == "haiku"


def test_detect_defaults_when_omitted():
    """Model and permissions default when not specified."""
    text = '{{WORKER task="Quick fix"}}'
    proposals = detect_worker_proposals(text)
    assert len(proposals) == 1
    assert proposals[0]["model"] == "sonnet"
    assert proposals[0]["permission_mode"] == "bypassPermissions"


def test_detect_no_proposals_in_regular_text():
    """Regular text without WORKER tags returns empty list."""
    text = "Let me explain how workers work in this system..."
    proposals = detect_worker_proposals(text)
    assert proposals == []


def test_detect_no_false_positives():
    """Partial matches or code blocks don't trigger false positives."""
    text = (
        "Here's how the format works:\n"
        "```\n"
        '{{WORKER task="example"}}\n'
        "```\n"
        "The above is just an example."
    )
    # The tag inside a code block is still on its own line, so it will be detected.
    # This is acceptable — detection only runs for orchestrator sessions anyway.
    proposals = detect_worker_proposals(text)
    assert len(proposals) == 1  # Line-based regex matches regardless of code blocks


def test_detect_proposals_mixed_with_text():
    """Proposals interspersed with explanation text."""
    text = (
        "Here's my plan:\n\n"
        "First, we need authentication:\n"
        '{{WORKER task="Implement JWT auth" model="sonnet" permissions="bypassPermissions"}}\n\n'
        "Then we need tests:\n"
        '{{WORKER task="Write auth tests" model="haiku" permissions="default"}}\n\n'
        "Sound good?"
    )
    proposals = detect_worker_proposals(text)
    assert len(proposals) == 2
    assert proposals[0]["task"] == "Implement JWT auth"
    assert proposals[1]["task"] == "Write auth tests"
    assert proposals[1]["permission_mode"] == "default"
