"""Command palette providers for the Re:Clawed app."""

from __future__ import annotations

from textual.command import DiscoveryHit, Hit, Hits, Provider


class ReclawedCommands(Provider):
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
        from reclawed.screens.chat import ChatScreen
        screen = self.app.screen
        if isinstance(screen, ChatScreen):
            screen.action_settings()

    async def _change_display_name(self) -> None:
        from reclawed.screens.chat import ChatScreen
        screen = self.app.screen
        if isinstance(screen, ChatScreen):
            screen.action_change_display_name()

    async def _spawn_worker_from_template(self) -> None:
        from reclawed.screens.chat import ChatScreen
        screen = self.app.screen
        if isinstance(screen, ChatScreen):
            screen.action_spawn_worker()
