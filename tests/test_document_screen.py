"""Tests for DocumentScreen and MemoryScreen utilities."""

from __future__ import annotations

import difflib
from pathlib import Path

import pytest

from reclawed.screens.document import DocumentScreen, _detect_language
from reclawed.screens.memory import _memory_dir_for_cwd, _human_size


# ---------------------------------------------------------------------------
# _detect_language
# ---------------------------------------------------------------------------

class TestDetectLanguage:
    def test_python_by_extension(self):
        assert _detect_language(Path("foo.py"), None) == "python"

    def test_markdown_by_extension(self):
        assert _detect_language(Path("README.md"), None) == "markdown"

    def test_markdown_long_extension(self):
        assert _detect_language(Path("notes.markdown"), None) == "markdown"

    def test_toml_by_extension(self):
        assert _detect_language(Path("config.toml"), None) == "toml"

    def test_yaml_by_extension(self):
        assert _detect_language(Path("ci.yaml"), None) == "yaml"

    def test_yml_by_extension(self):
        assert _detect_language(Path("ci.yml"), None) == "yaml"

    def test_css_by_extension(self):
        assert _detect_language(Path("style.css"), None) == "css"

    def test_tcss_mapped_to_css(self):
        assert _detect_language(Path("app.tcss"), None) == "css"

    def test_json_by_extension(self):
        assert _detect_language(Path("data.json"), None) == "json"

    def test_bash_by_extension(self):
        assert _detect_language(Path("script.sh"), None) == "bash"

    def test_rust_by_extension(self):
        assert _detect_language(Path("main.rs"), None) == "rust"

    def test_go_by_extension(self):
        assert _detect_language(Path("main.go"), None) == "go"

    def test_unknown_extension_returns_none(self):
        assert _detect_language(Path("file.xyz"), None) == None

    def test_no_path_returns_none(self):
        assert _detect_language(None, None) == None

    def test_diff_extension_returns_none(self, ):
        # .diff files are rendered via RichLog, not TextArea — no language
        assert _detect_language(Path("patch.diff"), None) == None

    def test_syntax_override_valid(self):
        assert _detect_language(Path("file.txt"), "python") == "python"

    def test_syntax_override_invalid_returns_none(self):
        assert _detect_language(Path("file.txt"), "cobol") == None

    def test_syntax_override_takes_precedence(self):
        # Override beats extension detection
        assert _detect_language(Path("file.py"), "markdown") == "markdown"

    def test_case_insensitive_extension(self):
        assert _detect_language(Path("FILE.PY"), None) == "python"


# ---------------------------------------------------------------------------
# _memory_dir_for_cwd
# ---------------------------------------------------------------------------

class TestMemoryDirForCwd:
    def test_none_cwd_returns_none(self):
        assert _memory_dir_for_cwd(None) is None

    def test_empty_string_returns_none(self):
        assert _memory_dir_for_cwd("") is None

    def test_unix_path_slug(self):
        result = _memory_dir_for_cwd("/Users/alice/projects/myapp")
        expected = Path.home() / ".claude" / "projects" / "-Users-alice-projects-myapp" / "memory"
        assert result == expected

    def test_root_path(self):
        result = _memory_dir_for_cwd("/")
        expected = Path.home() / ".claude" / "projects" / "-" / "memory"
        assert result == expected

    def test_path_without_leading_slash(self):
        result = _memory_dir_for_cwd("relative/path")
        expected = Path.home() / ".claude" / "projects" / "relative-path" / "memory"
        assert result == expected

    def test_windows_path_backslash_replaced(self):
        result = _memory_dir_for_cwd("C:\\Users\\alice\\project")
        expected = Path.home() / ".claude" / "projects" / "C:-Users-alice-project" / "memory"
        assert result == expected


# ---------------------------------------------------------------------------
# _human_size
# ---------------------------------------------------------------------------

class TestHumanSize:
    def test_bytes(self, tmp_path):
        f = tmp_path / "small.txt"
        f.write_bytes(b"x" * 500)
        assert _human_size(f) == "500B"

    def test_kilobytes(self, tmp_path):
        f = tmp_path / "medium.txt"
        f.write_bytes(b"x" * 2048)
        assert _human_size(f) == "2KB"

    def test_missing_file_returns_question_mark(self, tmp_path):
        f = tmp_path / "nonexistent.txt"
        assert _human_size(f) == "?"


# ---------------------------------------------------------------------------
# DocumentScreen constructor — no Textual app needed for pure data logic
# ---------------------------------------------------------------------------

class TestDocumentScreenInit:
    def test_content_from_string(self):
        screen = DocumentScreen(content="hello world", mode="view")
        assert screen._content == "hello world"
        assert screen._mode == "view"

    def test_content_from_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Title\nBody text")
        screen = DocumentScreen(path=f, mode="view")
        assert screen._content == "# Title\nBody text"
        assert screen._title == "test.md"

    def test_missing_file_gives_error_string(self, tmp_path):
        f = tmp_path / "missing.txt"
        screen = DocumentScreen(path=f, mode="view")
        assert "Error reading file" in screen._content or screen._content == ""

    def test_before_after_generates_diff(self):
        before = "line 1\nline 2\nline 3\n"
        after  = "line 1\nline 2 modified\nline 3\n"
        screen = DocumentScreen(before=before, after=after)
        assert screen._mode == "diff"
        assert "-line 2\n" in screen._content
        assert "+line 2 modified\n" in screen._content

    def test_before_after_forces_diff_mode(self):
        screen = DocumentScreen(before="a\n", after="b\n", mode="edit")
        # Even though mode="edit" was passed, before/after forces diff
        assert screen._mode == "diff"

    def test_explicit_title_overrides_filename(self, tmp_path):
        f = tmp_path / "config.toml"
        f.write_text("key = 'value'")
        screen = DocumentScreen(path=f, title="My Config")
        assert screen._title == "My Config"

    def test_title_defaults_to_filename(self, tmp_path):
        f = tmp_path / "notes.md"
        f.write_text("hello")
        screen = DocumentScreen(path=f)
        assert screen._title == "notes.md"

    def test_title_defaults_to_document_without_path(self):
        screen = DocumentScreen(content="raw text")
        assert screen._title == "Document"

    def test_line_count(self):
        text = "line1\nline2\nline3"
        screen = DocumentScreen(content=text)
        assert screen._line_count == 3

    def test_edit_mode_dirty_starts_false(self):
        screen = DocumentScreen(content="hello", mode="edit")
        assert screen._dirty is False

    def test_saved_starts_false(self):
        screen = DocumentScreen(content="hello", mode="edit")
        assert screen._saved is False

    def test_empty_content_with_no_inputs(self):
        screen = DocumentScreen()
        assert screen._content == ""

    def test_content_takes_priority_over_empty_path(self, tmp_path):
        # Path doesn't exist, content provided
        f = tmp_path / "ghost.md"
        screen = DocumentScreen(path=f, content="override content")
        # content param should be used since it's provided
        assert screen._content == "override content"


# ---------------------------------------------------------------------------
# Diff generation via difflib (sanity check)
# ---------------------------------------------------------------------------

class TestDiffGeneration:
    def test_unified_diff_has_hunk_markers(self):
        before = "a\nb\nc\n"
        after  = "a\nB\nc\n"
        diff = "".join(difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
        ))
        assert "@@" in diff
        assert "-b" in diff
        assert "+B" in diff

    def test_identical_content_produces_empty_diff(self):
        text = "same\n"
        diff = "".join(difflib.unified_diff(
            text.splitlines(keepends=True),
            text.splitlines(keepends=True),
        ))
        assert diff == ""
