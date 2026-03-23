"""Inline reaction prompt widget for orchestrator events.

Shown in the orchestrator's message list when reaction mode is "ask".
Presents action buttons for the user to choose how to handle an event.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message as TMessage
from textual.widgets import Button, Label


class ReactionPromptWidget(Vertical):
    """Inline prompt with action buttons for orchestrator events."""

    class ActionChosen(TMessage):
        """Posted when the user clicks an action button."""

        def __init__(
            self,
            worker_session_id: str,
            event_type: str,
            action: str,
            event_data: dict | None = None,
        ) -> None:
            super().__init__()
            self.worker_session_id = worker_session_id
            self.event_type = event_type
            self.action = action
            self.event_data = event_data or {}

    DEFAULT_CSS = """
    ReactionPromptWidget {
        height: auto;
        margin: 1 0;
        padding: 1 2;
        border-left: thick $warning;
        background: $surface-lighten-1;
    }
    ReactionPromptWidget .reaction-title {
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    ReactionPromptWidget .reaction-detail {
        color: $text-muted;
        margin-bottom: 1;
    }
    ReactionPromptWidget Horizontal {
        height: auto;
    }
    ReactionPromptWidget Button {
        margin-right: 1;
        min-width: 12;
    }
    """

    def __init__(
        self,
        event_type: str,
        title: str,
        detail: str,
        actions: list[tuple[str, str, str]],  # [(id, label, variant)]
        worker_session_id: str,
        event_data: dict | None = None,
    ) -> None:
        super().__init__()
        self._event_type = event_type
        self._title = title
        self._detail = detail
        self._actions = actions
        self._worker_session_id = worker_session_id
        self._event_data = event_data or {}

    def compose(self) -> ComposeResult:
        yield Label(self._title, classes="reaction-title")
        if self._detail:
            yield Label(self._detail, classes="reaction-detail")
        with Horizontal():
            for btn_id, label, variant in self._actions:
                yield Button(label, id=f"reaction-{btn_id}", variant=variant)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.id.removeprefix("reaction-") if event.button.id else ""
        self.post_message(self.ActionChosen(
            worker_session_id=self._worker_session_id,
            event_type=self._event_type,
            action=action,
            event_data=self._event_data,
        ))
        self.remove()


# ---------------------------------------------------------------------------
# Factory functions for common event types
# ---------------------------------------------------------------------------


def ci_failed_prompt(
    worker_session_id: str,
    worker_name: str,
    pr_number: int,
    attempt: int,
    event_data: dict | None = None,
) -> ReactionPromptWidget:
    return ReactionPromptWidget(
        event_type="ci_failed",
        title=f"CI Failed: {worker_name} (PR #{pr_number})",
        detail=f"Attempt {attempt}. Choose how to proceed:",
        actions=[
            ("fix", "Fix Automatically", "primary"),
            ("skip", "Skip", "default"),
            ("complete", "Mark Complete", "warning"),
        ],
        worker_session_id=worker_session_id,
        event_data=event_data,
    )


def changes_requested_prompt(
    worker_session_id: str,
    worker_name: str,
    pr_number: int,
    comment_count: int,
    event_data: dict | None = None,
) -> ReactionPromptWidget:
    return ReactionPromptWidget(
        event_type="changes_requested",
        title=f"Review comments on PR #{pr_number} ({worker_name})",
        detail=f"{comment_count} comment{'s' if comment_count != 1 else ''}:",
        actions=[
            ("route", "Route to Worker", "primary"),
            ("ignore", "Ignore", "default"),
        ],
        worker_session_id=worker_session_id,
        event_data=event_data,
    )


def approved_and_green_prompt(
    worker_session_id: str,
    worker_name: str,
    pr_number: int,
) -> ReactionPromptWidget:
    return ReactionPromptWidget(
        event_type="approved_and_green",
        title=f"PR #{pr_number} approved and CI passing! ({worker_name})",
        detail="",
        actions=[
            ("notify", "Notify Orchestrator", "primary"),
            ("dismiss", "Dismiss", "default"),
        ],
        worker_session_id=worker_session_id,
    )


def worker_timeout_prompt(
    worker_session_id: str,
    worker_name: str,
    minutes_running: int,
) -> ReactionPromptWidget:
    return ReactionPromptWidget(
        event_type="worker_timeout",
        title=f"Worker \"{worker_name}\" running for {minutes_running} minutes",
        detail="",
        actions=[
            ("complete", "Mark Complete", "primary"),
            ("extend", "Extend 30m", "default"),
            ("kill", "Kill", "error"),
        ],
        worker_session_id=worker_session_id,
    )
