#!/usr/bin/env python3
"""SessionStart Hook: Re:Clawed Project Status

Claude Code Event: SessionStart
Purpose: Display project status — git info, test count, feature progress
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def get_git_info(project_dir: Path) -> str:
    """Get git branch and recent changes."""
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=project_dir, timeout=5
        ).stdout.strip()

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=project_dir, timeout=5
        ).stdout.strip()

        changed = len(status.splitlines()) if status else 0

        log = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            capture_output=True, text=True, cwd=project_dir, timeout=5
        ).stdout.strip()

        return f"Branch: {branch} | {changed} uncommitted changes\nRecent commits:\n{log}"
    except Exception:
        return "Git info unavailable"


def count_features(project_dir: Path) -> str:
    """Count completed vs total features from FEATURES.md."""
    features_file = project_dir / "FEATURES.md"
    if not features_file.exists():
        return "FEATURES.md not found"

    done = 0
    total = 0
    for line in features_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- [x]"):
            done += 1
            total += 1
        elif stripped.startswith("- [ ]"):
            total += 1

    return f"Features: {done}/{total} completed ({total - done} remaining)"


def count_tests(project_dir: Path) -> str:
    """Count test files and test functions."""
    tests_dir = project_dir / "tests"
    if not tests_dir.exists():
        return "No tests/ directory"

    test_files = list(tests_dir.rglob("test_*.py"))
    test_count = 0
    for f in test_files:
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("def test_") or line.strip().startswith("async def test_"):
                test_count += 1

    return f"Tests: {test_count} test functions in {len(test_files)} files"


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() if not sys.stdin.isatty() else "{}")
    except Exception:
        payload = {}

    project_dir = Path(payload.get("cwd", ".")).resolve()
    if not (project_dir / "src" / "reclawed").exists():
        # Not in reclawed project
        print(json.dumps({"continue": True}))
        return

    git_info = get_git_info(project_dir)
    features = count_features(project_dir)
    tests = count_tests(project_dir)

    status_msg = f"""Re:Clawed Project Status
========================
{git_info}
{features}
{tests}

Key skills loaded: textual-tui, python-async, websocket-relay, claude-sdk
Agents available: tui-developer, feature-developer, code-reviewer
Commands: /test, /lint, /status, /features"""

    print(json.dumps({
        "continue": True,
        "systemMessage": status_msg,
    }))


if __name__ == "__main__":
    main()
