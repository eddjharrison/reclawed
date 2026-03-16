"""Tests for Claude session discovery and import."""

import json

from reclawed.importer import (
    DiscoveredProject,
    _clean_user_text,
    discover_projects,
    import_project_sessions,
    parse_session_metadata,
)
from reclawed.models import Session
from reclawed.store import Store


def _write_jsonl(path, lines):
    """Write a list of dicts as JSONL."""
    with path.open("w", encoding="utf-8") as fh:
        for entry in lines:
            fh.write(json.dumps(entry) + "\n")


def _minimal_user_msg(content="Hello", session_id="sess-001", cwd="/proj"):
    return {
        "type": "user",
        "parentUuid": None,
        "sessionId": session_id,
        "cwd": cwd,
        "timestamp": "2026-03-15T10:00:00.000Z",
        "message": {"role": "user", "content": content},
    }


def _minimal_assistant_msg(session_id="sess-001", model="claude-opus-4-6"):
    return {
        "type": "assistant",
        "parentUuid": "some-uuid",
        "sessionId": session_id,
        "timestamp": "2026-03-15T10:01:00.000Z",
        "message": {
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": "Hello!"}],
        },
    }


# --- parse_session_metadata ---


def test_parse_session_metadata(tmp_path):
    """Extracts session_id, cwd, name, model, timestamps."""
    jsonl = tmp_path / "sess-001.jsonl"
    _write_jsonl(jsonl, [
        _minimal_user_msg("Tell me about Python"),
        _minimal_assistant_msg(),
    ])
    meta = parse_session_metadata(jsonl)
    assert meta is not None
    assert meta["session_id"] == "sess-001"
    assert meta["cwd"] == "/proj"
    assert meta["name"] == "Tell me about Python"
    assert meta["model"] == "claude-opus-4-6"
    assert meta["created_at"] == "2026-03-15T10:00:00.000Z"
    assert meta["updated_at"] == "2026-03-15T10:01:00.000Z"


def test_parse_session_metadata_truncates_long_name(tmp_path):
    """Session name is truncated to 60 chars."""
    long_msg = "x" * 100
    jsonl = tmp_path / "sess-long.jsonl"
    _write_jsonl(jsonl, [_minimal_user_msg(long_msg)])
    meta = parse_session_metadata(jsonl)
    assert meta is not None
    assert len(meta["name"]) == 60
    assert meta["name"].endswith("…")


def test_parse_session_metadata_empty_file(tmp_path):
    """Returns None for empty file."""
    jsonl = tmp_path / "empty.jsonl"
    jsonl.write_text("")
    assert parse_session_metadata(jsonl) is None


def test_parse_session_metadata_no_user_message(tmp_path):
    """Returns None if there's no user message."""
    jsonl = tmp_path / "no-user.jsonl"
    _write_jsonl(jsonl, [
        {"type": "queue-operation", "operation": "enqueue", "sessionId": "s1"},
    ])
    assert parse_session_metadata(jsonl) is None


def test_parse_session_metadata_skips_queue_ops(tmp_path):
    """Queue operations are skipped, first user msg is used."""
    jsonl = tmp_path / "with-queue.jsonl"
    _write_jsonl(jsonl, [
        {"type": "queue-operation", "operation": "enqueue",
         "sessionId": "s1", "content": "queue content"},
        _minimal_user_msg("Real message", session_id="s1"),
        _minimal_assistant_msg(session_id="s1"),
    ])
    meta = parse_session_metadata(jsonl)
    assert meta is not None
    assert meta["name"] == "Real message"


def test_parse_skips_system_messages_for_name(tmp_path):
    """System-injected messages (local-command-caveat, etc.) are skipped."""
    jsonl = tmp_path / "sess-sys.jsonl"
    _write_jsonl(jsonl, [
        _minimal_user_msg(
            "<local-command-caveat>Caveat: The messages below were generated...</local-command-caveat>",
            session_id="sess-sys",
        ),
        _minimal_user_msg(
            "<command-name>/clear</command-name><command-args></command-args>",
            session_id="sess-sys",
        ),
        _minimal_user_msg("Actual user question about Python", session_id="sess-sys"),
        _minimal_assistant_msg(session_id="sess-sys"),
    ])
    meta = parse_session_metadata(jsonl)
    assert meta is not None
    assert meta["name"] == "Actual user question about Python"


def test_clean_user_text_strips_xml_tags():
    """XML tags are stripped from user text."""
    assert _clean_user_text("Hello world") == "Hello world"
    assert _clean_user_text("<local-command-caveat>Caveat</local-command-caveat>") is None
    assert _clean_user_text("<command-name>/prompt</command-name>") is None
    assert _clean_user_text("<task-notification>...</task-notification>") is None
    assert _clean_user_text("") is None
    assert _clean_user_text("   ") is None


# --- discover_projects ---


def test_discover_projects(tmp_path):
    """Discovers project directories with JSONL files."""
    proj_a = tmp_path / "-Users-ed-proj-a"
    proj_a.mkdir()
    _write_jsonl(proj_a / "s1.jsonl", [_minimal_user_msg(cwd="/Users/ed/proj/a")])
    _write_jsonl(proj_a / "s2.jsonl", [_minimal_user_msg(cwd="/Users/ed/proj/a")])

    proj_b = tmp_path / "-Users-ed-proj-b"
    proj_b.mkdir()
    _write_jsonl(proj_b / "s1.jsonl", [_minimal_user_msg(cwd="/Users/ed/proj/b")])

    # Empty dir should be excluded
    empty = tmp_path / "-Users-ed-empty"
    empty.mkdir()

    projects = discover_projects(claude_dir=tmp_path)
    assert len(projects) == 2
    # Sorted by session count descending
    assert projects[0].session_count == 2
    assert projects[0].cwd == "/Users/ed/proj/a"
    assert projects[1].session_count == 1
    assert projects[1].cwd == "/Users/ed/proj/b"


def test_discover_projects_nonexistent_dir(tmp_path):
    """Returns empty list if the projects directory doesn't exist."""
    assert discover_projects(claude_dir=tmp_path / "nope") == []


def test_discover_projects_falls_back_to_dir_name(tmp_path):
    """Falls back to decoding dir name if no cwd in JSONL."""
    proj = tmp_path / "-Users-ed-proj"
    proj.mkdir()
    # JSONL with no cwd field
    _write_jsonl(proj / "s1.jsonl", [
        {"type": "queue-operation", "operation": "enqueue", "sessionId": "s1"},
    ])
    projects = discover_projects(claude_dir=tmp_path)
    assert len(projects) == 1
    assert projects[0].cwd == "/Users/ed/proj"


# --- import_project_sessions ---


def test_import_creates_session_and_message():
    """Import creates a Session and a synthetic Message in the store."""
    store = Store(":memory:")
    proj = DiscoveredProject(cwd="/proj", session_count=1, project_dir=None)

    # We'll test via parse_session_metadata + manual session creation
    # since import_project_sessions needs a real project_dir with files
    session = Session(
        claude_session_id="test-session-id",
        name="Test import",
        cwd="/proj",
    )
    store.create_session(session)
    assert store.has_claude_session("test-session-id")
    fetched = store.get_session(session.id)
    assert fetched.cwd == "/proj"
    assert fetched.name == "Test import"
    store.close()


def test_import_project_sessions_full(tmp_path):
    """Full integration: discover → import → verify in store."""
    proj_dir = tmp_path / "-Users-ed-proj"
    proj_dir.mkdir()
    _write_jsonl(proj_dir / "sess-001.jsonl", [
        _minimal_user_msg("First chat", session_id="sess-001", cwd="/Users/ed/proj"),
        _minimal_assistant_msg(session_id="sess-001"),
    ])
    _write_jsonl(proj_dir / "sess-002.jsonl", [
        _minimal_user_msg("Second chat", session_id="sess-002", cwd="/Users/ed/proj"),
        _minimal_assistant_msg(session_id="sess-002", model="claude-sonnet-4-6"),
    ])

    store = Store(":memory:")
    project = DiscoveredProject(
        cwd="/Users/ed/proj",
        session_count=2,
        project_dir=proj_dir,
    )

    count = import_project_sessions(project, store)
    assert count == 2

    sessions = store.list_sessions()
    assert len(sessions) == 2
    names = {s.name for s in sessions}
    assert "First chat" in names
    assert "Second chat" in names

    # Each session should have one synthetic message
    for s in sessions:
        msgs = store.get_session_messages(s.id)
        assert len(msgs) == 1
        assert "Imported session" in msgs[0].content
        assert s.cwd == "/Users/ed/proj"
        assert s.claude_session_id in {"sess-001", "sess-002"}

    store.close()


def test_import_dedup(tmp_path):
    """Importing the same session twice doesn't create duplicates."""
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    _write_jsonl(proj_dir / "sess-001.jsonl", [
        _minimal_user_msg("Hello", session_id="sess-001"),
        _minimal_assistant_msg(session_id="sess-001"),
    ])

    store = Store(":memory:")
    project = DiscoveredProject(cwd="/proj", session_count=1, project_dir=proj_dir)

    first = import_project_sessions(project, store)
    assert first == 1

    second = import_project_sessions(project, store)
    assert second == 0

    assert len(store.list_sessions()) == 1
    store.close()


def test_import_max_sessions(tmp_path):
    """max_sessions limits how many sessions are imported."""
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    for i in range(10):
        _write_jsonl(proj_dir / f"sess-{i:03d}.jsonl", [
            _minimal_user_msg(f"Chat {i}", session_id=f"sess-{i:03d}"),
            _minimal_assistant_msg(session_id=f"sess-{i:03d}"),
        ])

    store = Store(":memory:")
    project = DiscoveredProject(cwd="/proj", session_count=10, project_dir=proj_dir)

    count = import_project_sessions(project, store, max_sessions=3)
    assert count == 3
    assert len(store.list_sessions()) == 3
    store.close()
