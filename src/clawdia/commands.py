"""Command palette providers for the Re:Clawed app."""

from __future__ import annotations

from textual.command import DiscoveryHit, Hit, Hits, Provider


class ClawdiaCommands(Provider):
    """Adds Re:Clawed-specific commands to the command palette."""

    async def discover(self) -> Hits:
        yield DiscoveryHit(
            display="Settings",
            command=self._open_settings,
            help="Manage workspaces, import sessions, and configure preferences",
        )
        yield DiscoveryHit(
            display="Change Display Name",
            command=self._change_display_name,
            help="Update your participant name shown in group chats",
        )
        yield DiscoveryHit(
            display="Import Workspaces",
            command=self._open_settings,
            help="Discover and import Claude sessions from other projects",
        )
        yield DiscoveryHit(
            display="Spawn Worker from Template...",
            command=self._spawn_worker_from_template,
            help="Open the worker spawner with template selection",
        )
        yield DiscoveryHit(
            display="Browse Memory Files (Ctrl+M)",
            command=self._open_memory_browser,
            help="View and edit Claude's per-project memory files",
        )
        yield DiscoveryHit(
            display="Open File... (Ctrl+O)",
            command=self._open_file,
            help="Open any file in the document viewer",
        )
        yield DiscoveryHit(
            display="Code Review (Ctrl+R)",
            command=self._review_code,
            help="Review git diffs — working tree, branch compare, or PR",
        )

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)

        commands = [
            ("Settings", self._open_settings,
             "Manage workspaces, import sessions, and configure preferences"),
            ("Change Display Name", self._change_display_name,
             "Update your participant name shown in group chats"),
            ("Import Workspaces", self._open_settings,
             "Discover and import Claude sessions from other projects"),
            ("Spawn Worker from Template...", self._spawn_worker_from_template,
             "Open the worker spawner with template selection"),
            ("Browse Memory Files (Ctrl+M)", self._open_memory_browser,
             "View and edit Claude's per-project memory files"),
            ("Open File... (Ctrl+O)", self._open_file,
             "Open any file in the document viewer"),
            ("Code Review (Ctrl+R)", self._review_code,
             "Review git diffs — working tree, branch compare, or PR"),
        ]

        for display, callback, help_text in commands:
            match = matcher.match(display)
            if match > 0:
                yield Hit(
                    match,
                    matcher.highlight(display),
                    callback,
                    help=help_text,
                )

    async def _open_settings(self) -> None:
        from clawdia.screens.chat import ChatScreen
        screen = self.app.screen
        if isinstance(screen, ChatScreen):
            screen.action_settings()

    async def _change_display_name(self) -> None:
        from clawdia.screens.chat import ChatScreen
        screen = self.app.screen
        if isinstance(screen, ChatScreen):
            screen.action_change_display_name()

    async def _spawn_worker_from_template(self) -> None:
        from clawdia.screens.chat import ChatScreen
        screen = self.app.screen
        if isinstance(screen, ChatScreen):
            screen.action_spawn_worker()

    async def _open_memory_browser(self) -> None:
        from clawdia.screens.chat import ChatScreen
        screen = self.app.screen
        if isinstance(screen, ChatScreen):
            screen.action_memory_browser()

    async def _open_file(self) -> None:
        from clawdia.screens.chat import ChatScreen
        screen = self.app.screen
        if isinstance(screen, ChatScreen):
            screen.action_open_file()

    async def _review_code(self) -> None:
        from clawdia.screens.chat import ChatScreen
        screen = self.app.screen
        if isinstance(screen, ChatScreen):
            screen.action_review_code()
