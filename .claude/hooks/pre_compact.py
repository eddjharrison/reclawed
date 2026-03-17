#!/usr/bin/env python3
"""PreCompact Hook: Context Preservation Warning

Claude Code Event: PreCompact
Purpose: Remind about important context before compaction clears it
"""

from __future__ import annotations

import json
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def main() -> None:
    try:
        _ = json.loads(sys.stdin.read() if not sys.stdin.isatty() else "{}")
    except Exception:
        pass

    print(json.dumps({
        "continue": True,
        "systemMessage": (
            "PreCompact: Context window is being compacted. "
            "Key project facts to preserve:\n"
            "- Re:Clawed is a WhatsApp-style TUI for Claude CLI built with Python/Textual\n"
            "- Source: src/reclawed/ | Widgets: src/reclawed/widgets/ | Screens: src/reclawed/screens/\n"
            "- Config: config.toml (TOML) | Store: SQLite | Relay: WebSocket daemon\n"
            "- Windows quirks: CREATE_NO_WINDOW for subprocesses, some emoji break rendering\n"
            "- Working emoji: 📁🔋🧠🤖⚡ | Broken: ⚙🔀🔒⬤\n"
            "- No dock:bottom abuse (compression bugs) — use natural vertical flow\n"
            "- Run /status to reload project context after compaction."
        ),
    }))


if __name__ == "__main__":
    main()
