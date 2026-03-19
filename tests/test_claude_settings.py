"""Tests for MCP forwarding methods on ClaudeSession."""

from unittest.mock import AsyncMock
import asyncio


async def test_session_get_mcp_status():
    """ClaudeSession.get_mcp_status forwards to SDK client."""
    from reclawed.claude_session import ClaudeSession

    s = object.__new__(ClaudeSession)
    s._ready = asyncio.Event()
    s._ready.set()
    s._client = AsyncMock()
    s._client.get_mcp_status = AsyncMock(return_value={"mcpServers": []})

    result = await s.get_mcp_status()
    assert result == {"mcpServers": []}
    s._client.get_mcp_status.assert_awaited_once()


async def test_session_toggle_mcp_server():
    from reclawed.claude_session import ClaudeSession

    s = object.__new__(ClaudeSession)
    s._ready = asyncio.Event()
    s._ready.set()
    s._client = AsyncMock()

    await s.toggle_mcp_server("my-srv", False)
    s._client.toggle_mcp_server.assert_awaited_once_with("my-srv", False)


async def test_session_reconnect_mcp_server():
    from reclawed.claude_session import ClaudeSession

    s = object.__new__(ClaudeSession)
    s._ready = asyncio.Event()
    s._ready.set()
    s._client = AsyncMock()

    await s.reconnect_mcp_server("my-srv")
    s._client.reconnect_mcp_server.assert_awaited_once_with("my-srv")


async def test_session_mcp_no_client_raises():
    import pytest
    from reclawed.claude_session import ClaudeSession

    s = object.__new__(ClaudeSession)
    s._ready = asyncio.Event()
    s._ready.set()
    s._client = None

    with pytest.raises(RuntimeError, match="not connected"):
        await s.get_mcp_status()
