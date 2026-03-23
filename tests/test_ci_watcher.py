"""Tests for CI watcher state machine and event dispatch."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from clawdia.ci_watcher import (
    CIWatcherState,
    CIPassEvent,
    CIFailEvent,
    CICommentEvent,
    CIRetryExhaustedEvent,
    run_ci_watcher,
)
from clawdia.git_utils import CICheck, CIStatus


async def test_ci_pass_emits_event():
    state = CIWatcherState(
        worker_session_id="w1", pr_number=42, cwd="/tmp",
        poll_interval=0.01,
    )
    events = []

    async def on_event(e):
        events.append(e)
        state.stopped = True

    with patch("clawdia.ci_watcher.git_pr_checks") as mock_checks, \
         patch("clawdia.ci_watcher.git_pr_review_comments", return_value=[]):
        mock_checks.return_value = CIStatus(overall="pass", checks=[], pr_number=42)
        await run_ci_watcher(state, on_event)

    assert len(events) == 1
    assert isinstance(events[0], CIPassEvent)
    assert events[0].worker_session_id == "w1"


async def test_ci_fail_emits_event_with_logs():
    state = CIWatcherState(
        worker_session_id="w1", pr_number=42, cwd="/tmp",
        poll_interval=0.01, retries_remaining=1,
    )
    events = []

    async def on_event(e):
        events.append(e)
        state.stopped = True  # stop after first event

    failed_check = CICheck(name="lint", status="fail", url="")
    with patch("clawdia.ci_watcher.git_pr_checks") as mock_checks, \
         patch("clawdia.ci_watcher.git_pr_check_logs", return_value="Error: lint failed"), \
         patch("clawdia.ci_watcher.git_pr_review_comments", return_value=[]):
        mock_checks.return_value = CIStatus(
            overall="fail", checks=[failed_check], pr_number=42,
        )
        await run_ci_watcher(state, on_event)

    assert len(events) == 1
    assert isinstance(events[0], CIFailEvent)
    assert events[0].logs == "Error: lint failed"
    assert len(events[0].failed_checks) == 1
    assert state.retries_remaining == 0
    assert state.retries_used == 1


async def test_ci_retry_exhausted():
    state = CIWatcherState(
        worker_session_id="w1", pr_number=42, cwd="/tmp",
        poll_interval=0.01, retries_remaining=0,
    )
    events = []

    async def on_event(e):
        events.append(e)

    with patch("clawdia.ci_watcher.git_pr_checks") as mock_checks, \
         patch("clawdia.ci_watcher.git_pr_review_comments", return_value=[]):
        mock_checks.return_value = CIStatus(
            overall="fail",
            checks=[CICheck(name="test", status="fail", url="")],
            pr_number=42,
        )
        await run_ci_watcher(state, on_event)

    assert len(events) == 1
    assert isinstance(events[0], CIRetryExhaustedEvent)


async def test_ci_comment_event():
    state = CIWatcherState(
        worker_session_id="w1", pr_number=42, cwd="/tmp",
        poll_interval=0.01,
    )
    events = []

    async def on_event(e):
        events.append(e)
        # Stop after receiving comment event
        if isinstance(e, CICommentEvent):
            state.stopped = True

    comments = [{"author": "reviewer", "body": "Fix this", "path": "foo.py", "created_at": "2026-01-01T00:00:00"}]

    with patch("clawdia.ci_watcher.git_pr_checks") as mock_checks, \
         patch("clawdia.ci_watcher.git_pr_review_comments") as mock_comments:
        mock_checks.return_value = CIStatus(overall="pending", checks=[], pr_number=42)
        mock_comments.return_value = comments
        await run_ci_watcher(state, on_event)

    comment_events = [e for e in events if isinstance(e, CICommentEvent)]
    assert len(comment_events) == 1
    assert comment_events[0].comments == comments


def test_watcher_state_defaults():
    state = CIWatcherState(worker_session_id="w1", pr_number=1, cwd="/tmp")
    assert state.poll_interval == 30.0
    assert state.max_interval == 300.0
    assert state.retries_remaining == 2
    assert state.stopped is False
    assert state.last_ci_status is None


async def test_stopped_watcher_exits():
    state = CIWatcherState(
        worker_session_id="w1", pr_number=42, cwd="/tmp",
        poll_interval=0.01, stopped=True,
    )
    events = []

    async def on_event(e):
        events.append(e)

    await run_ci_watcher(state, on_event)
    assert events == []
