"""Tests for McpManagerScreen._handle_action button-ID parsing (finding #5).

These tests exercise the pure parsing/guard logic in _handle_action without
mounting the full Textual screen (which requires a running App).
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# _MCP_ACTIONS whitelist
# ---------------------------------------------------------------------------

def test_mcp_actions_whitelist_exists():
    """_MCP_ACTIONS set is exported from the module."""
    from clawdia.screens.mcp_manager import _MCP_ACTIONS

    assert isinstance(_MCP_ACTIONS, set)
    assert _MCP_ACTIONS == {"auth", "enable", "disable", "reconnect", "remove"}


def test_mcp_actions_whitelist_rejects_unknown():
    """Actions not in _MCP_ACTIONS are rejected."""
    from clawdia.screens.mcp_manager import _MCP_ACTIONS

    assert "cancel" not in _MCP_ACTIONS
    assert "save" not in _MCP_ACTIONS
    assert "close" not in _MCP_ACTIONS
    assert "btn-mcp-auth" not in _MCP_ACTIONS  # full ID, not just action word


# ---------------------------------------------------------------------------
# Button ID parsing logic (mirrors _handle_action internals)
# ---------------------------------------------------------------------------

def _parse_mcp_bid(bid: str, server_list: list) -> tuple[str, int, dict] | None:
    """Replicate the _handle_action parsing so we can unit-test it in isolation."""
    from clawdia.screens.mcp_manager import _MCP_ACTIONS

    parts = bid.split("-", 3)
    if len(parts) < 4:
        return None
    action = parts[2]
    if action not in _MCP_ACTIONS:
        return None
    try:
        idx = int(parts[3])
    except ValueError:
        return None
    if idx < 0 or idx >= len(server_list):
        return None
    return action, idx, server_list[idx]


_SERVERS = [
    {"name": "filesystem", "scope": "project"},
    {"name": "github", "scope": "user"},
    {"name": "claude.ai Gmail", "scope": "local"},
]


def test_parse_valid_auth_button():
    result = _parse_mcp_bid("btn-mcp-auth-0", _SERVERS)
    assert result is not None
    action, idx, info = result
    assert action == "auth"
    assert idx == 0
    assert info["name"] == "filesystem"


def test_parse_valid_enable_button():
    result = _parse_mcp_bid("btn-mcp-enable-1", _SERVERS)
    assert result is not None
    action, idx, info = result
    assert action == "enable"
    assert idx == 1
    assert info["name"] == "github"


def test_parse_valid_disable_button():
    result = _parse_mcp_bid("btn-mcp-disable-2", _SERVERS)
    assert result is not None
    action, idx, _ = result
    assert action == "disable"
    assert idx == 2


def test_parse_valid_reconnect_button():
    result = _parse_mcp_bid("btn-mcp-reconnect-0", _SERVERS)
    assert result is not None
    action, idx, _ = result
    assert action == "reconnect"
    assert idx == 0


def test_parse_valid_remove_button():
    result = _parse_mcp_bid("btn-mcp-remove-2", _SERVERS)
    assert result is not None
    action, _, info = result
    assert action == "remove"
    assert info["name"] == "claude.ai Gmail"  # server names with spaces/dots work fine


def test_parse_rejects_unknown_action():
    """Unrecognised action word (e.g. 'cancel') is rejected by whitelist."""
    assert _parse_mcp_bid("btn-mcp-cancel-0", _SERVERS) is None


def test_parse_rejects_too_few_parts():
    """Button IDs with fewer than 4 dash-separated parts are rejected."""
    assert _parse_mcp_bid("btn-mcp-auth", _SERVERS) is None   # missing index
    assert _parse_mcp_bid("btn-mcp", _SERVERS) is None
    assert _parse_mcp_bid("btn-close-mcp", _SERVERS) is None


def test_parse_rejects_non_integer_index():
    """Non-integer index (e.g. server name used as suffix) is rejected."""
    assert _parse_mcp_bid("btn-mcp-auth-github", _SERVERS) is None
    assert _parse_mcp_bid("btn-mcp-enable-one", _SERVERS) is None


def test_parse_rejects_negative_index():
    """Negative index is out of bounds and rejected."""
    assert _parse_mcp_bid("btn-mcp-auth--1", _SERVERS) is None


def test_parse_rejects_out_of_bounds_index():
    """Index >= len(server_list) is rejected."""
    assert _parse_mcp_bid("btn-mcp-auth-3", _SERVERS) is None   # len is 3, max idx=2
    assert _parse_mcp_bid("btn-mcp-auth-99", _SERVERS) is None


def test_parse_empty_server_list():
    """Any index is out of bounds when server_list is empty."""
    assert _parse_mcp_bid("btn-mcp-auth-0", []) is None


def test_parse_close_button_not_routed():
    """btn-close-mcp is handled by a separate branch, not _handle_action."""
    # The on_button_pressed guard is `bid.startswith("btn-mcp-")` — this ID
    # starts with "btn-close" so it would never reach _handle_action.
    assert not "btn-close-mcp".startswith("btn-mcp-")


def test_safe_id_removed():
    """_safe_id was dead code and must no longer exist in the module."""
    import clawdia.screens.mcp_manager as mod

    assert not hasattr(mod, "_safe_id"), (
        "_safe_id is dead code that was removed in the PR review; "
        "it should not be present in mcp_manager"
    )
