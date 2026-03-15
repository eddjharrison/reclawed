"""Main Textual application."""

from __future__ import annotations

from textual.app import App

from reclawed.config import Config
from reclawed.screens.chat import ChatScreen
from reclawed.store import Store


class ReclawedApp(App):
    """Re:Clawed — WhatsApp-style TUI for Claude CLI."""

    TITLE = "Re:Clawed"
    SUB_TITLE = "Claude Chat TUI"
    CSS_PATH = "styles/app.tcss"

    def __init__(self, config: Config | None = None, resume_session_id: str | None = None) -> None:
        super().__init__()
        self.config = config or Config()
        self.store = Store(self.config.db_path)
        self._resume_session_id = resume_session_id

    def on_mount(self) -> None:
        # Apply the configured theme before the screen appears.
        self.theme = self.config.textual_theme

        session = None
        if self._resume_session_id:
            session = self.store.get_session(self._resume_session_id)
        elif self._resume_session_id is None:
            # Check for --continue: get most recent session
            pass
        self.push_screen(ChatScreen(self.store, self.config, session))

    def on_unmount(self) -> None:
        self.store.close()
