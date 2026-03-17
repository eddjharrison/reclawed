"""Context menu modal shown on right-click of a session row."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static


# Actions exposed by the context menu.
ACTION_MARK_UNREAD = "mark_unread"
ACTION_MUTE = "mute"
ACTION_UNMUTE = "unmute"
ACTION_ARCHIVE = "archive"
ACTION_DELETE = "delete"
ACTION_RENAME = "rename"
ACTION_GENERATE_NAME = "generate_name"
ACTION_PIN = "pin"
ACTION_UNPIN = "unpin"
ACTION_SPAWN_WORKER = "spawn_worker"
ACTION_MARK_WORKER_COMPLETE = "mark_worker_complete"
ACTION_ENABLE_ORCHESTRATOR = "enable_orchestrator"


class ContextMenu(ModalScreen[tuple[str, str] | None]):
    """Modal screen showing session-level actions.

    Dismisses with ``(action, session_id)`` when an option is selected, or
    ``None`` when the user cancels with Escape.

    Example::

        result = await self.app.push_screen_wait(
            ContextMenu(session_id="abc", is_muted=False)
        )
        if result:
            action, sid = result
    """

    DEFAULT_CSS = """
    ContextMenu {
        align: center middle;
    }
    ContextMenu > #context-dialog {
        width: 40;
        height: auto;
        max-height: 20;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    ContextMenu #context-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: $text-muted;
        margin-bottom: 1;
    }
    ContextMenu ListView {
        width: 100%;
        height: auto;
        border: none;
        background: $surface;
    }
    ContextMenu ListItem {
        padding: 0 1;
    }
    ContextMenu ListItem:hover {
        background: $primary 30%;
    }
    ContextMenu #action-delete Label {
        color: $error;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        session_id: str,
        is_muted: bool = False,
        is_pinned: bool = False,
        session_type: str | None = None,
        worker_status: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._session_id = session_id
        self._is_muted = is_muted
        self._is_pinned = is_pinned
        self._session_type = session_type
        self._worker_status = worker_status

    def compose(self) -> ComposeResult:
        mute_label = "Unmute" if self._is_muted else "Mute"
        mute_action = ACTION_UNMUTE if self._is_muted else ACTION_MUTE
        pin_label = "Unpin" if self._is_pinned else "Pin to top"
        pin_action = ACTION_UNPIN if self._is_pinned else ACTION_PIN

        actions: list[tuple[str, str, str]] = [
            (pin_action,         pin_label,         "action-pin"),
            (ACTION_MARK_UNREAD, "Mark as Unread", "action-mark-unread"),
            (mute_action,        mute_label,       "action-mute"),
            (ACTION_ARCHIVE,     "Archive",         "action-archive"),
            (ACTION_RENAME,      "Rename",          "action-rename"),
            (ACTION_GENERATE_NAME, "Generate name",  "action-generate-name"),
        ]

        # Orchestrator/worker actions
        if self._session_type is None:
            actions.append(
                (ACTION_ENABLE_ORCHESTRATOR, "Enable Orchestrator", "action-enable-orchestrator")
            )
        if self._session_type != "worker":
            actions.append(
                (ACTION_SPAWN_WORKER, "Spawn Worker", "action-spawn-worker")
            )
        if self._session_type == "worker" and self._worker_status != "complete":
            actions.append(
                (ACTION_MARK_WORKER_COMPLETE, "Mark Complete", "action-mark-complete")
            )

        actions.append(
            (ACTION_DELETE,      "Delete",          "action-delete"),
        )

        items: list[ListItem] = []
        for action_key, label_text, item_id in actions:
            item = ListItem(Label(label_text), id=item_id)
            # Stash the action key on the item for retrieval in the handler.
            item._action_key = action_key  # type: ignore[attr-defined]
            items.append(item)

        with Static(id="context-dialog"):
            yield Label("Session Actions", id="context-title")
            yield ListView(*items, id="context-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        action_key = getattr(event.item, "_action_key", None)
        if action_key:
            self.dismiss((action_key, self._session_id))

    def action_cancel(self) -> None:
        self.dismiss(None)
