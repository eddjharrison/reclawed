"""Tests for git_utils — diff parsing, dataclasses, and error handling."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from clawdia.git_utils import (
    ChangedFile,
    DiffHunk,
    FileDiff,
    _run_git,
    parse_unified_diff,
)

# ---------------------------------------------------------------------------
# Fixtures: realistic diff text
# ---------------------------------------------------------------------------

MULTI_FILE_DIFF = """\
diff --git a/src/app.py b/src/app.py
index abc1234..def5678 100644
--- a/src/app.py
+++ b/src/app.py
@@ -10,6 +10,8 @@ import logging
 from pathlib import Path

 log = logging.getLogger(__name__)
+
+TIMEOUT = 30


 class App:
@@ -25,7 +27,7 @@ class App:
         self.running = False

     def start(self):
-        self.running = True
+        self.running = self._validate() and True
         log.info("App started")

     def stop(self):
diff --git a/tests/test_app.py b/tests/test_app.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/tests/test_app.py
@@ -0,0 +1,12 @@
+\"\"\"Tests for app module.\"\"\"
+
+from src.app import App
+
+
+def test_start():
+    app = App()
+    app.start()
+    assert app.running
+
+def test_stop():
+    pass
"""

RENAME_DIFF = """\
diff --git a/old_name.py b/new_name.py
similarity index 95%
rename from old_name.py
rename to new_name.py
index abc1234..def5678 100644
--- a/old_name.py
+++ b/new_name.py
@@ -1,3 +1,4 @@
 def hello():
-    print("old")
+    print("new")
+    return True
"""

BINARY_DIFF = """\
diff --git a/image.png b/image.png
new file mode 100644
index 0000000..abcdef1
Binary files /dev/null and b/image.png differ
diff --git a/src/code.py b/src/code.py
index 1234567..abcdef0 100644
--- a/src/code.py
+++ b/src/code.py
@@ -1,2 +1,3 @@
 x = 1
+y = 2
 z = 3
"""


# ---------------------------------------------------------------------------
# parse_unified_diff tests
# ---------------------------------------------------------------------------


class TestParseUnifiedDiff:
    def test_multi_file_diff(self):
        result = parse_unified_diff(MULTI_FILE_DIFF)
        assert len(result) == 2

        # First file: src/app.py
        app_diff = result[0]
        assert app_diff.path == "src/app.py"
        assert app_diff.old_path is None
        assert len(app_diff.hunks) == 2
        assert app_diff.additions == 3  # +TIMEOUT, +blank line, +modified line
        assert app_diff.deletions == 1  # -old line

        # Check hunk headers
        assert app_diff.hunks[0].old_start == 10
        assert app_diff.hunks[0].old_count == 6
        assert app_diff.hunks[0].new_start == 10
        assert app_diff.hunks[0].new_count == 8

        assert app_diff.hunks[1].old_start == 25
        assert app_diff.hunks[1].old_count == 7
        assert app_diff.hunks[1].new_start == 27
        assert app_diff.hunks[1].new_count == 7

        # Second file: tests/test_app.py (new file)
        test_diff = result[1]
        assert test_diff.path == "tests/test_app.py"
        assert test_diff.additions == 12
        assert test_diff.deletions == 0

    def test_rename(self):
        result = parse_unified_diff(RENAME_DIFF)
        assert len(result) == 1

        fd = result[0]
        assert fd.path == "new_name.py"
        assert fd.old_path == "old_name.py"
        assert fd.additions == 2
        assert fd.deletions == 1
        assert len(fd.hunks) == 1

    def test_empty_diff(self):
        assert parse_unified_diff("") == []
        assert parse_unified_diff("   \n\n  ") == []

    def test_binary_files_skipped(self):
        result = parse_unified_diff(BINARY_DIFF)
        # Binary file (image.png) should be skipped; only code.py remains.
        assert len(result) == 1
        assert result[0].path == "src/code.py"
        assert result[0].additions == 1
        assert result[0].deletions == 0

    def test_hunk_lines_include_header(self):
        result = parse_unified_diff(MULTI_FILE_DIFF)
        hunk = result[0].hunks[0]
        assert hunk.lines[0].startswith("@@")

    def test_single_line_count_defaults(self):
        """When a hunk has count omitted (implies 1), parsing should handle it."""
        diff = """\
diff --git a/f.py b/f.py
index 0000000..1111111 100644
--- a/f.py
+++ b/f.py
@@ -1 +1,2 @@
 original
+added
"""
        result = parse_unified_diff(diff)
        assert len(result) == 1
        hunk = result[0].hunks[0]
        assert hunk.old_count == 1
        assert hunk.new_count == 2


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_changed_file(self):
        cf = ChangedFile(path="foo.py", additions=10, deletions=3, status="M")
        assert cf.path == "foo.py"
        assert cf.additions == 10
        assert cf.deletions == 3
        assert cf.status == "M"

    def test_file_diff_additions_deletions(self):
        hunk = DiffHunk(
            header="@@ -1,3 +1,4 @@",
            old_start=1,
            old_count=3,
            new_start=1,
            new_count=4,
            lines=[
                "@@ -1,3 +1,4 @@",
                " context",
                "-removed",
                "+added1",
                "+added2",
            ],
        )
        fd = FileDiff(path="test.py", old_path=None, hunks=[hunk], raw="...")
        assert fd.additions == 2
        assert fd.deletions == 1

    def test_file_diff_ignores_plusplus_minusminus(self):
        """The +++ and --- header lines should not count as adds/deletes."""
        hunk = DiffHunk(
            header="@@ -1,2 +1,2 @@",
            old_start=1,
            old_count=2,
            new_start=1,
            new_count=2,
            lines=[
                "@@ -1,2 +1,2 @@",
                "--- a/file.py",
                "+++ b/file.py",
                "-old",
                "+new",
            ],
        )
        fd = FileDiff(path="file.py", old_path=None, hunks=[hunk], raw="...")
        assert fd.additions == 1
        assert fd.deletions == 1

    def test_diff_hunk_default_lines(self):
        hunk = DiffHunk(
            header="@@ -1,1 +1,1 @@",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
        )
        assert hunk.lines == []


# ---------------------------------------------------------------------------
# _run_git error handling
# ---------------------------------------------------------------------------


class TestRunGit:
    @pytest.mark.asyncio
    async def test_run_git_raises_on_failure(self, tmp_path):
        """_run_git should raise RuntimeError when the process exits non-zero."""
        # Use a real directory but not a git repo — git will fail with rc!=0.
        with pytest.raises(RuntimeError, match="Command failed"):
            await _run_git(["git", "log", "--oneline", "-1"], cwd=str(tmp_path))

    @pytest.mark.asyncio
    async def test_run_git_returns_stdout(self, tmp_path):
        """_run_git should return decoded stdout on success."""
        # Initialise a throwaway repo with an initial commit so HEAD exists.
        for cmd in [
            ["git", "init", str(tmp_path)],
            ["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"],
        ]:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        branch = await _run_git(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(tmp_path),
        )
        assert branch.strip()  # should be "main" or "master"
