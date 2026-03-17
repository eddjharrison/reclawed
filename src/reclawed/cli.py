"""CLI entry point using click."""

from __future__ import annotations

import os
import sys
import warnings
import click

# Suppress asyncio ResourceWarnings on Windows (unclosed subprocess transports
# during garbage collection at exit — harmless but noisy).
warnings.filterwarnings("ignore", category=ResourceWarning)

from reclawed.app import ReclawedApp
from reclawed.config import Config


@click.command()
@click.option("--continue", "continue_session", is_flag=True, help="Resume the most recent session")
@click.option("--session", "session_id", default=None, help="Resume a specific session by ID")
@click.version_option(package_name="reclawed")
def main(continue_session: bool, session_id: str | None) -> None:
    """Re:Clawed — WhatsApp-style TUI for Claude CLI."""
    config = Config.load()

    resume_id = session_id
    if continue_session and not resume_id:
        # Find the most recent session
        from reclawed.store import Store
        store = Store(config.db_path)
        sessions = store.list_sessions()
        store.close()
        if sessions:
            resume_id = sessions[0].id

    app = ReclawedApp(config=config, resume_session_id=resume_id)
    app.run()

    # Suppress noisy asyncio tracebacks on Windows during cleanup
    if sys.platform == "win32":
        try:
            sys.stderr = open(os.devnull, "w")
        except Exception:
            pass
