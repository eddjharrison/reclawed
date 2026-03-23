"""CI feedback loop — watches worker PRs for status changes.

Pure-logic module with no TUI dependencies. ChatScreen creates
watcher instances and handles their events.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from clawdia.git_utils import CICheck, CIStatus, git_pr_checks, git_pr_check_logs, git_pr_review_comments

log = logging.getLogger(__name__)


@dataclass
class CIWatcherState:
    """Persistent state for a CI watcher on one worker session."""

    worker_session_id: str
    pr_number: int
    cwd: str
    poll_interval: float = 30.0
    base_interval: float = 30.0
    max_interval: float = 300.0
    retries_remaining: int = 2
    retries_used: int = 0
    last_ci_status: str | None = None
    last_comment_timestamp: str | None = None
    stopped: bool = False


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


@dataclass
class CIEvent:
    """Base class for CI watcher events."""

    worker_session_id: str


@dataclass
class CIPassEvent(CIEvent):
    """CI checks passed."""

    ci_status: CIStatus | None = None


@dataclass
class CIFailEvent(CIEvent):
    """CI checks failed."""

    failed_checks: list[CICheck] = field(default_factory=list)
    logs: str = ""


@dataclass
class CICommentEvent(CIEvent):
    """New review comments on the PR."""

    comments: list[dict] = field(default_factory=list)


@dataclass
class CIRetryExhaustedEvent(CIEvent):
    """All retry attempts exhausted — CI still failing."""

    failed_checks: list[CICheck] = field(default_factory=list)


# Type alias for the callback
EventCallback = Callable[[CIEvent], Awaitable[None]]


async def run_ci_watcher(
    state: CIWatcherState,
    on_event: EventCallback,
) -> None:
    """Poll CI status for a worker's PR with exponential backoff.

    Calls *on_event* when status changes. Runs until stopped or resolved.
    """
    log.info(
        "CI watcher started for PR #%d (worker %s)",
        state.pr_number, state.worker_session_id,
    )

    while not state.stopped:
        await asyncio.sleep(state.poll_interval)

        if state.stopped:
            break

        try:
            ci_status = await git_pr_checks(state.pr_number, state.cwd)

            if ci_status.overall == "pass" and state.last_ci_status != "pass":
                state.last_ci_status = "pass"
                await on_event(CIPassEvent(
                    worker_session_id=state.worker_session_id,
                    ci_status=ci_status,
                ))
                return  # done — CI passed

            elif ci_status.overall == "fail" and state.last_ci_status != "fail":
                state.last_ci_status = "fail"
                if state.retries_remaining > 0:
                    # Fetch failure logs
                    logs = await git_pr_check_logs(state.pr_number, state.cwd)
                    state.retries_remaining -= 1
                    state.retries_used += 1
                    await on_event(CIFailEvent(
                        worker_session_id=state.worker_session_id,
                        failed_checks=ci_status.failed_checks,
                        logs=logs,
                    ))
                    # Reset status so we detect the next result after fix
                    state.last_ci_status = "fixing"
                    # Reset poll interval for faster detection after fix push
                    state.poll_interval = state.base_interval
                    continue
                else:
                    await on_event(CIRetryExhaustedEvent(
                        worker_session_id=state.worker_session_id,
                        failed_checks=ci_status.failed_checks,
                    ))
                    return  # done — retries exhausted

            # Check for new review comments
            comments = await git_pr_review_comments(
                state.pr_number, state.cwd, since=state.last_comment_timestamp,
            )
            if comments:
                state.last_comment_timestamp = max(
                    c.get("created_at", "") for c in comments
                )
                await on_event(CICommentEvent(
                    worker_session_id=state.worker_session_id,
                    comments=comments,
                ))

            # Exponential backoff on no change
            state.poll_interval = min(
                state.poll_interval * 1.5,
                state.max_interval,
            )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning(
                "CI watcher error for PR #%d: %s", state.pr_number, exc,
            )
            # Back off more aggressively on errors
            state.poll_interval = min(
                state.poll_interval * 2,
                state.max_interval,
            )

    log.info("CI watcher stopped for PR #%d", state.pr_number)
