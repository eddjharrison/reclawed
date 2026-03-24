"""Tests for relay daemon lifecycle management."""

import json
import os
import time

import pytest

from clawdia.relay.daemon import (
    _info_path,
    _pid_alive,
    _port_responsive,
    _write_daemon_info,
    ensure_daemon,
    get_daemon_info,
    is_daemon_running,
    start_daemon,
    stop_daemon,
)


def test_get_daemon_info_no_file(tmp_path):
    """Returns None when no info file exists."""
    assert get_daemon_info(tmp_path) is None


def test_get_daemon_info_with_file(tmp_path):
    """Reads the daemon info file correctly."""
    info = {"pid": 12345, "port": 8765, "token": "abc"}
    _write_daemon_info(tmp_path, info)
    loaded = get_daemon_info(tmp_path)
    assert loaded == info


def test_is_daemon_running_no_file(tmp_path):
    """Returns False when no info file exists."""
    assert is_daemon_running(tmp_path) is False


def test_is_daemon_running_stale_pid(tmp_path):
    """Returns False and cleans up when PID is dead."""
    _write_daemon_info(tmp_path, {"pid": 999999, "port": 59999, "token": "x"})
    assert is_daemon_running(tmp_path) is False
    # Info file should be cleaned up
    assert get_daemon_info(tmp_path) is None


def test_pid_alive_current_process():
    """Current process PID should be alive."""
    assert _pid_alive(os.getpid()) is True


def test_pid_alive_bogus():
    """Bogus PID should not be alive."""
    assert _pid_alive(999999) is False


def test_port_responsive_unbound():
    """An unbound port should not be responsive."""
    assert _port_responsive(59999, timeout=0.1) is False


# --- Integration tests (spawn real daemon) ---


@pytest.mark.slow
def test_start_and_stop_daemon(tmp_path):
    """Start a real daemon, verify it's running, then stop it."""
    # Use a high port to avoid conflicts
    port = 18765
    info = start_daemon(port=port, token="test-token", data_dir=tmp_path)

    assert info["pid"] > 0
    assert info["port"] == port
    assert info["token"] == "test-token"

    # Daemon should be responsive
    assert _port_responsive(port)
    assert is_daemon_running(tmp_path)

    # Info file should exist
    loaded = get_daemon_info(tmp_path)
    assert loaded is not None
    assert loaded["pid"] == info["pid"]

    # Stop the daemon
    assert stop_daemon(tmp_path) is True
    # Give the process time to fully exit
    for _ in range(20):
        if not _pid_alive(info["pid"]):
            break
        time.sleep(0.1)
    assert not _pid_alive(info["pid"])


@pytest.mark.slow
def test_ensure_daemon_starts_if_not_running(tmp_path):
    """ensure_daemon starts a daemon when none is running."""
    port = 18766
    info = ensure_daemon(data_dir=tmp_path, port=port)

    assert info["pid"] > 0
    assert info["port"] == port
    assert info["token"]  # auto-generated

    # Clean up
    stop_daemon(tmp_path)


@pytest.mark.slow
def test_ensure_daemon_reuses_if_running(tmp_path):
    """ensure_daemon returns existing daemon if already running."""
    port = 18767
    info1 = ensure_daemon(data_dir=tmp_path, port=port)
    info2 = ensure_daemon(data_dir=tmp_path, port=port)

    # Same PID — didn't start a second daemon
    assert info1["pid"] == info2["pid"]
    assert info1["token"] == info2["token"]

    # Clean up
    stop_daemon(tmp_path)


@pytest.mark.slow
def test_ensure_daemon_preserves_token_across_restart(tmp_path):
    """Token is preserved when daemon is stopped and restarted."""
    port = 18768
    info1 = ensure_daemon(data_dir=tmp_path, port=port)
    token = info1["token"]

    stop_daemon(tmp_path)
    time.sleep(0.3)

    info2 = ensure_daemon(data_dir=tmp_path, port=port)
    assert info2["token"] == token  # same token reused

    stop_daemon(tmp_path)


@pytest.mark.slow
def test_daemon_creates_db_file(tmp_path):
    """Daemon creates relay.db for message persistence."""
    port = 18769
    ensure_daemon(data_dir=tmp_path, port=port)

    db_file = tmp_path / "relay.db"
    assert db_file.exists()

    stop_daemon(tmp_path)


@pytest.mark.slow
def test_stop_daemon_already_stopped(tmp_path):
    """Stopping a non-running daemon returns True."""
    assert stop_daemon(tmp_path) is True
