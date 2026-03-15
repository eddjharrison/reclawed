"""Tests for Claude process stream parsing."""

import json

import pytest

from reclawed.claude import ClaudeProcess, StreamResult, StreamSessionId, StreamToken


@pytest.fixture
def mock_stream_lines():
    """Simulated stream-json lines from claude CLI."""
    return [
        json.dumps({
            "type": "system",
            "session_id": "test-session-123",
        }),
        json.dumps({
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "Hello "},
        }),
        json.dumps({
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "world!"},
        }),
        json.dumps({
            "type": "result",
            "result": "Hello world!",
            "total_cost_usd": 0.001,
            "duration_ms": 500,
            "modelUsage": {
                "claude-sonnet-4-20250514": {
                    "inputTokens": 10,
                    "outputTokens": 5,
                },
            },
        }),
    ]


def test_claude_process_init():
    cp = ClaudeProcess()
    assert cp._binary == "claude"


def test_claude_process_custom_binary():
    cp = ClaudeProcess(claude_binary="/usr/local/bin/claude")
    assert cp._binary == "/usr/local/bin/claude"


def test_stream_lines_are_valid_json(mock_stream_lines):
    for line in mock_stream_lines:
        parsed = json.loads(line)
        assert "type" in parsed
