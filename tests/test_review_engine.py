"""Tests for the AI code review annotation engine."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reclawed.review_engine import (
    Annotation,
    FileReview,
    format_review_markdown,
    review_diff,
    review_file,
)


# ---------------------------------------------------------------------------
# Annotation dataclass
# ---------------------------------------------------------------------------


class TestAnnotation:
    def test_emoji_error(self):
        a = Annotation(hunk_index=0, severity="error", comment="bug")
        assert a.emoji == "\U0001f41b"

    def test_emoji_warning(self):
        a = Annotation(hunk_index=0, severity="warning", comment="smell")
        assert a.emoji == "\u26a0\ufe0f"

    def test_emoji_info(self):
        a = Annotation(hunk_index=0, severity="info", comment="note")
        assert a.emoji == "\U0001f4a1"

    def test_emoji_praise(self):
        a = Annotation(hunk_index=0, severity="praise", comment="nice")
        assert a.emoji == "\u2705"

    def test_emoji_unknown_fallback(self):
        a = Annotation(hunk_index=0, severity="unknown", comment="?")
        assert a.emoji == "\U0001f4ac"


# ---------------------------------------------------------------------------
# FileReview dataclass
# ---------------------------------------------------------------------------


class TestFileReview:
    def test_has_issues_with_error(self):
        fr = FileReview(
            path="a.py",
            annotations=[Annotation(hunk_index=0, severity="error", comment="bad")],
        )
        assert fr.has_issues is True

    def test_has_issues_with_warning(self):
        fr = FileReview(
            path="a.py",
            annotations=[Annotation(hunk_index=0, severity="warning", comment="iffy")],
        )
        assert fr.has_issues is True

    def test_no_issues_info_only(self):
        fr = FileReview(
            path="a.py",
            annotations=[Annotation(hunk_index=0, severity="info", comment="fyi")],
        )
        assert fr.has_issues is False

    def test_no_issues_praise_only(self):
        fr = FileReview(
            path="a.py",
            annotations=[Annotation(hunk_index=0, severity="praise", comment="great")],
        )
        assert fr.has_issues is False

    def test_no_issues_empty(self):
        fr = FileReview(path="a.py")
        assert fr.has_issues is False


# ---------------------------------------------------------------------------
# format_review_markdown
# ---------------------------------------------------------------------------


class TestFormatReviewMarkdown:
    def test_with_annotations(self):
        reviews = [
            FileReview(
                path="src/foo.py",
                summary="Looks mostly fine.",
                annotations=[
                    Annotation(hunk_index=0, severity="error", comment="Null deref"),
                    Annotation(hunk_index=1, severity="warning", comment="Unused var"),
                    Annotation(hunk_index=0, severity="praise", comment="Good guard"),
                ],
            ),
            FileReview(
                path="src/bar.py",
                summary="Clean code.",
                annotations=[],
            ),
        ]
        md = format_review_markdown(reviews, title="PR Review")
        assert "## PR Review" in md
        assert "3 annotations" in md
        assert "1 errors" in md
        assert "1 warnings" in md
        assert "### `src/foo.py`" in md
        assert "### `src/bar.py`" in md
        assert "**ERROR**" in md
        assert "**WARNING**" in md
        assert "**PRAISE**" in md
        assert "Reviewed by Re:Clawed" in md

    def test_with_suggestion(self):
        reviews = [
            FileReview(
                path="x.py",
                summary="Fix needed.",
                annotations=[
                    Annotation(hunk_index=0, severity="error", comment="Off by one", suggestion="range(n - 1)"),
                ],
            ),
        ]
        md = format_review_markdown(reviews)
        assert "```suggestion" in md
        assert "range(n - 1)" in md

    def test_empty_reviews(self):
        md = format_review_markdown([])
        assert "## Code Review" in md
        assert "0 annotations" in md
        assert "0 errors" in md


# ---------------------------------------------------------------------------
# review_file (mocked API)
# ---------------------------------------------------------------------------


def _make_mock_response(text: str):
    """Build a mock Anthropic response with content[0].text = text."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


class TestReviewFile:
    async def test_valid_json_response(self):
        payload = json.dumps(
            {
                "summary": "Good code overall.",
                "annotations": [
                    {"hunk_index": 0, "severity": "info", "comment": "Consider a docstring", "suggestion": None},
                    {"hunk_index": 1, "severity": "error", "comment": "Missing null check"},
                ],
            }
        )
        mock_response = _make_mock_response(payload)
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            result = await review_file("test.py", "--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old\n+new")

        assert result.path == "test.py"
        assert result.summary == "Good code overall."
        assert len(result.annotations) == 2
        assert result.annotations[0].severity == "info"
        assert result.annotations[1].severity == "error"
        assert result.has_issues is True

    async def test_json_wrapped_in_code_fence(self):
        payload = '```json\n{"summary": "OK", "annotations": []}\n```'
        mock_response = _make_mock_response(payload)
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            result = await review_file("f.py", "diff text")

        assert result.summary == "OK"
        assert result.annotations == []

    async def test_invalid_json_response(self):
        mock_response = _make_mock_response("This is not JSON at all!")
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            result = await review_file("bad.py", "diff text")

        assert result.path == "bad.py"
        assert "not valid JSON" in result.summary

    async def test_api_error(self):
        import anthropic

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APIError(
                message="rate limited",
                request=MagicMock(),
                body=None,
            )
        )

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            result = await review_file("err.py", "diff text")

        assert result.path == "err.py"
        assert "API error" in result.summary


# ---------------------------------------------------------------------------
# review_diff with callback
# ---------------------------------------------------------------------------


class TestReviewDiff:
    async def test_callback_called_per_file(self):
        mock_review = FileReview(path="a.py", summary="ok")

        async def fake_review_file(file_path, diff_text, model="sonnet", context=None):
            return FileReview(path=file_path, summary="reviewed")

        file_diffs = [
            SimpleNamespace(path="a.py", raw="diff a"),
            SimpleNamespace(path="b.py", raw="diff b"),
            SimpleNamespace(path="c.py", raw="diff c"),
        ]

        callback = MagicMock()

        with patch("reclawed.review_engine.review_file", side_effect=fake_review_file):
            results = await review_diff(file_diffs, on_file_reviewed=callback)

        assert len(results) == 3
        assert callback.call_count == 3
        # Verify each file's path was passed to the callback
        called_paths = [call.args[0] for call in callback.call_args_list]
        assert called_paths == ["a.py", "b.py", "c.py"]
