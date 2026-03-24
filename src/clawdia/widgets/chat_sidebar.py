"""Sidebar container listing all chat sessions with live search filtering."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.events import Click
from textual.message import Message as TMessage
from textual.widgets import Input, Label, Static

from clawdia.config import Workspace
from clawdia.models import Session
from clawdia.store import Store
from clawdia.widgets.chat_list_item import ChatListItem
from clawdia.widgets.workspace_section import WorkspaceSection


class ChatSidebar(Vertical):
    """Left-hand sidebar that lists sessions and supports search filtering.

    Layout::

        Vertical (ChatSidebar)
          Input  (search)
          VerticalScroll (chat-list)
            ChatListItem ...
            ChatListItem ...

    Messages posted:
    - ``ChatSidebar.SessionSelected(session_id)`` when a row is clicked
    - ``ChatSidebar.NewChatRequested()``          when Ctrl+N is pressed
    """

    DEFAULT_CSS = """
    ChatSidebar {
        height: 100%;
        background: $surface;
        border-right: solid $primary 30%;
    }
    ChatSidebar Input {
        width: 100%;
        height: 3;
        border: solid $primary 30%;
        background: $surface;
    }
    ChatSidebar #chat-list {
        width: 100%;
        height: 1fr;
    }
    ChatSidebar .completed-toggle {
        width: 100%;
        height: 1;
        padding: 0 1;
        color: $text-disabled;
        text-style: italic;
    }
    ChatSidebar .completed-toggle:hover {
        color: $text-muted;
        background: $primary 10%;
    }
    """

    BINDINGS = [
        Binding("ctrl+n", "new_chat", "New Chat", show=True),
        Binding("m", "context_menu", "Menu", show=False),
    ]

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    class SessionSelected(TMessage):
        """Posted when the user clicks a session row."""

        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    class NewChatRequested(TMessage):
        """Posted when the user wants to start a new chat."""

    class ContextMenuRequested(TMessage):
        """Posted when a context menu is requested on a session."""

        def __init__(self, session_id: str, is_muted: bool, is_pinned: bool = False) -> None:
            super().__init__()
            self.session_id = session_id
            self.is_muted = is_muted
            self.is_pinned = is_pinned

    class SessionRenamed(TMessage):
        """Posted when a session is renamed via inline edit."""

        def __init__(self, session_id: str, new_name: str) -> None:
            super().__init__()
            self.session_id = session_id
            self.new_name = new_name

    class NewChatInWorkspace(TMessage):
        """Posted when '+ New Chat' is clicked inside a workspace section."""

        def __init__(self, cwd: str | None) -> None:
            super().__init__()
            self.cwd = cwd

    class RemoveWorkspaceRequested(TMessage):
        """Posted when the user wants to remove a workspace from the sidebar."""

        def __init__(self, cwd: str, name: str) -> None:
            super().__init__()
            self.cwd = cwd
            self.name = name

    class RefreshWorkspaceRequested(TMessage):
        """Posted when the user wants to re-import sessions for a workspace."""

        def __init__(self, cwd: str, name: str) -> None:
            super().__init__()
            self.cwd = cwd
            self.name = name

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, store: Store, workspaces: list[Workspace] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._store = store
        self._workspaces = workspaces or []
        # Ordered list of all sessions (refreshed from the store)
        self._sessions: list[Session] = []
        # Map session_id -> last assistant/user message preview
        self._previews: dict[str, str] = {}
        # The session_id that is currently open in the chat pane
        self._active_id: str | None = None
        # Current search query (lowercased)
        self._search_query: str = ""
        # Track which orchestrators have their completed workers expanded
        self._expanded_orchestrators: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search chats...", id="sidebar-search")
        yield VerticalScroll(id="chat-list")

    def on_mount(self) -> None:
        self.refresh_sessions()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh_sessions(self, active_session_id: str | None = None) -> None:
        """Re-query the store and rebuild the chat list.

        Call this after any session-level mutation (new session, rename, delete,
        etc.).  ``active_session_id`` sets which row is highlighted; passing
        ``None`` keeps the previous active session.
        """
        if active_session_id is not None:
            self._active_id = active_session_id

        all_sessions = self._store.list_sessions()
        # Hide empty sessions (no messages) unless they're the active one or a worker
        self._sessions = [
            s for s in all_sessions
            if s.message_count > 0 or s.id == self._active_id
            or s.session_type == "worker"
        ]

        # Build preview text for each session from its last message.
        self._previews.clear()
        for session in self._sessions:
            last = self._store.get_last_message(session.id)
            self._previews[session.id] = last.content if last is not None else ""

        self._rebuild_list()

    def set_active(self, session_id: str) -> None:
        """Highlight ``session_id`` as the currently open session."""
        self._active_id = session_id
        chat_list = self.query_one("#chat-list", VerticalScroll)
        for item in chat_list.query(ChatListItem):
            is_active = item.session_id == session_id
            if is_active:
                item.refresh_data(is_active=True)
                item.scroll_visible()
            else:
                item.refresh_data(is_active=False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_list(self) -> None:
        """Clear and repopulate the scroll pane, honouring the search filter."""
        chat_list = self.query_one("#chat-list", VerticalScroll)
        chat_list.remove_children()

        visible, completed_counts = self._filtered_sessions_collapsed()

        if not self._workspaces:
            # No workspaces configured — flat list (100% backward compatible)
            for session in visible:
                preview = self._previews.get(session.id, "")
                is_active = session.id == self._active_id
                chat_list.mount(
                    ChatListItem(session, last_preview=preview, is_active=is_active)
                )
                # Insert "(N completed)" toggle after an orchestrator with hidden workers
                if session.id in completed_counts:
                    count = completed_counts[session.id]
                    expanded = session.id in self._expanded_orchestrators
                    label_text = f"    \u25bc {count} completed" if expanded else f"    \u25b6 {count} completed"
                    toggle = Label(label_text, classes="completed-toggle")
                    toggle._orch_id = session.id  # type: ignore[attr-defined]
                    chat_list.mount(toggle)
            return

        # Group sessions by workspace cwd
        ws_expanded = {ws.expanded_path: ws for ws in self._workspaces}
        grouped: dict[str, list[Session]] = {ws.expanded_path: [] for ws in self._workspaces}
        ungrouped: list[Session] = []

        for session in visible:
            if session.cwd and session.cwd in ws_expanded:
                grouped[session.cwd].append(session)
            else:
                ungrouped.append(session)

        # Render workspace sections — only expand the one containing the active session
        for ws in self._workspaces:
            sessions_in_ws = grouped[ws.expanded_path]
            if not sessions_in_ws and self._search_query:
                continue  # Hide empty sections during search
            has_active = any(s.id == self._active_id for s in sessions_in_ws)
            section = WorkspaceSection(
                workspace_name=ws.name,
                cwd=ws.expanded_path,
                collapsed=not has_active,
                color=ws.color or "cyan",
            )
            chat_list.mount(section)
            container = section.items_container
            for session in sessions_in_ws:
                preview = self._previews.get(session.id, "")
                is_active = session.id == self._active_id
                container.mount(
                    ChatListItem(session, last_preview=preview, is_active=is_active)
                )
                if session.id in completed_counts:
                    count = completed_counts[session.id]
                    expanded = session.id in self._expanded_orchestrators
                    label_text = f"    \u25bc {count} completed" if expanded else f"    \u25b6 {count} completed"
                    toggle = Label(label_text, classes="completed-toggle")
                    toggle._orch_id = session.id  # type: ignore[attr-defined]
                    container.mount(toggle)

        # Render ungrouped sessions under "Default" section
        if ungrouped:
            has_active = any(s.id == self._active_id for s in ungrouped)
            section = WorkspaceSection(
                workspace_name="Default",
                cwd=None,
                collapsed=not has_active,
                color="white",
            )
            chat_list.mount(section)
            container = section.items_container
            for session in ungrouped:
                preview = self._previews.get(session.id, "")
                is_active = session.id == self._active_id
                container.mount(
                    ChatListItem(session, last_preview=preview, is_active=is_active)
                )
                if session.id in completed_counts:
                    count = completed_counts[session.id]
                    expanded = session.id in self._expanded_orchestrators
                    label_text = f"    \u25bc {count} completed" if expanded else f"    \u25b6 {count} completed"
                    toggle = Label(label_text, classes="completed-toggle")
                    toggle._orch_id = session.id  # type: ignore[attr-defined]
                    container.mount(toggle)

    def _filtered_sessions_collapsed(self) -> tuple[list[Session], dict[str, int]]:
        """Return sessions with completed workers collapsed, plus hidden counts."""
        sessions, completed_counts = self._order_with_workers_collapsed(self._sessions)
        if not self._search_query:
            return sessions, completed_counts
        q = self._search_query
        filtered = [s for s in sessions if q in s.name.lower()]
        return filtered, completed_counts

    @staticmethod
    def _order_with_workers(sessions: list[Session]) -> list[Session]:
        """Reorder sessions so workers appear directly after their orchestrator.

        Non-worker sessions keep their original order (pinned DESC, updated_at DESC).
        Workers are inserted after their parent, ordered by created_at ASC.
        """
        # Separate workers from non-workers
        workers_by_parent: dict[str, list[Session]] = {}
        non_workers: list[Session] = []
        for s in sessions:
            if s.session_type == "worker" and s.parent_session_id:
                workers_by_parent.setdefault(s.parent_session_id, []).append(s)
            else:
                non_workers.append(s)

        if not workers_by_parent:
            return non_workers

        # Sort each group of workers by created_at ASC
        for parent_id in workers_by_parent:
            workers_by_parent[parent_id].sort(key=lambda w: w.created_at)

        # Insert workers after their parent
        result: list[Session] = []
        for s in non_workers:
            result.append(s)
            if s.id in workers_by_parent:
                result.extend(workers_by_parent[s.id])

        return result

    def _order_with_workers_collapsed(self, sessions: list[Session]) -> tuple[list[Session], dict[str, int]]:
        """Like _order_with_workers but collapses completed workers.

        Returns (ordered_sessions, completed_counts) where completed_counts
        maps orchestrator_id -> number of hidden completed workers.
        Running workers are always shown. Completed workers only shown if
        the orchestrator is in _expanded_orchestrators.
        """
        workers_by_parent: dict[str, list[Session]] = {}
        non_workers: list[Session] = []
        for s in sessions:
            if s.session_type == "worker" and s.parent_session_id:
                workers_by_parent.setdefault(s.parent_session_id, []).append(s)
            else:
                non_workers.append(s)

        if not workers_by_parent:
            return non_workers, {}

        for parent_id in workers_by_parent:
            workers_by_parent[parent_id].sort(key=lambda w: w.created_at)

        result: list[Session] = []
        completed_counts: dict[str, int] = {}
        for s in non_workers:
            result.append(s)
            if s.id in workers_by_parent:
                workers = workers_by_parent[s.id]
                running = [w for w in workers if w.worker_status != "complete"]
                completed = [w for w in workers if w.worker_status == "complete"]

                # Always show running workers
                result.extend(running)

                if completed:
                    if s.id in self._expanded_orchestrators:
                        # Show all completed workers when expanded
                        result.extend(completed)
                    else:
                        # Collapse — just record the count
                        completed_counts[s.id] = len(completed)

        return result, completed_counts

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "sidebar-search":
            self._search_query = event.value.strip().lower()
            self._rebuild_list()

    def on_click(self, event: Click) -> None:
        """Handle clicks on completed-toggle labels."""
        target = event.widget
        if target is not None and hasattr(target, "_orch_id"):
            event.stop()
            orch_id = target._orch_id  # type: ignore[attr-defined]
            if orch_id in self._expanded_orchestrators:
                self._expanded_orchestrators.discard(orch_id)
            else:
                self._expanded_orchestrators.add(orch_id)
            self._rebuild_list()

    def on_chat_list_item_clicked(self, event: ChatListItem.Clicked) -> None:
        event.stop()
        self.post_message(self.SessionSelected(event.session_id))

    def on_chat_list_item_context_menu_requested(self, event: ChatListItem.ContextMenuRequested) -> None:
        event.stop()
        self.post_message(self.ContextMenuRequested(event.session_id, event.is_muted))

    def on_chat_list_item_renamed(self, event: ChatListItem.Renamed) -> None:
        event.stop()
        self.post_message(self.SessionRenamed(event.session_id, event.new_name))

    def on_workspace_section_new_chat_in_workspace(self, event: WorkspaceSection.NewChatInWorkspace) -> None:
        event.stop()
        self.post_message(self.NewChatInWorkspace(event.cwd))

    def on_workspace_section_remove_workspace_requested(self, event: WorkspaceSection.RemoveWorkspaceRequested) -> None:
        event.stop()
        self.post_message(self.RemoveWorkspaceRequested(event.cwd, event.name))

    def on_workspace_section_refresh_workspace_requested(self, event: WorkspaceSection.RefreshWorkspaceRequested) -> None:
        event.stop()
        self.post_message(self.RefreshWorkspaceRequested(event.cwd, event.name))

    def start_rename(self, session_id: str) -> None:
        """Trigger inline rename on the ChatListItem for the given session."""
        chat_list = self.query_one("#chat-list", VerticalScroll)
        for item in chat_list.query(ChatListItem):
            if item.session_id == session_id:
                self.app.call_later(item.start_rename)
                break

    def action_new_chat(self) -> None:
        self.post_message(self.NewChatRequested())

    def action_context_menu(self) -> None:
        """Open context menu for the active session in the sidebar."""
        if self._active_id:
            session = next((s for s in self._sessions if s.id == self._active_id), None)
            if session:
                self.post_message(self.ContextMenuRequested(session.id, session.muted, session.pinned))
