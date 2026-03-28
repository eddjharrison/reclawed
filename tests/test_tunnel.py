"""Tests for Cloudflare tunnel management (named and quick tunnels)."""

import json
import os
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clawdia.config import Config
from clawdia.relay.tunnel import (
    has_cloudflared,
    is_logged_in,
    tunnel_exists,
    generate_tunnel_config,
    get_tunnel_url,
    ensure_tunnel,
    start_named_tunnel,
    stop_named_tunnel,
    start_quick_tunnel,
    stop_quick_tunnel,
    ensure_quick_tunnel,
    _pid_alive,
    _find_credentials_file,
    _DEFAULT_CREDENTIALS_DIR,
)


# ---------------------------------------------------------------------------
# has_cloudflared / is_logged_in
# ---------------------------------------------------------------------------

def test_has_cloudflared_present():
    with patch("clawdia.relay.tunnel.shutil.which", return_value="/usr/local/bin/cloudflared"):
        assert has_cloudflared() is True


def test_has_cloudflared_missing():
    with patch("clawdia.relay.tunnel.shutil.which", return_value=None):
        assert has_cloudflared() is False


def test_is_logged_in_with_cert(tmp_path):
    cert = tmp_path / "cert.pem"
    cert.touch()
    with patch("clawdia.relay.tunnel._DEFAULT_CREDENTIALS_DIR", tmp_path):
        assert is_logged_in() is True


def test_is_logged_in_without_cert(tmp_path):
    with patch("clawdia.relay.tunnel._DEFAULT_CREDENTIALS_DIR", tmp_path):
        assert is_logged_in() is False


# ---------------------------------------------------------------------------
# tunnel_exists
# ---------------------------------------------------------------------------

def test_tunnel_exists_found():
    tunnel_json = json.dumps([{"id": "abc-123-def", "name": "clawdia-relay"}])
    mock_result = MagicMock(returncode=0, stdout=tunnel_json)
    with patch("clawdia.relay.tunnel.subprocess.run", return_value=mock_result):
        uuid = tunnel_exists("clawdia-relay")
    assert uuid == "abc-123-def"


def test_tunnel_exists_not_found():
    mock_result = MagicMock(returncode=0, stdout="[]")
    with patch("clawdia.relay.tunnel.subprocess.run", return_value=mock_result):
        assert tunnel_exists("nonexistent") is None


def test_tunnel_exists_error():
    mock_result = MagicMock(returncode=1, stdout="", stderr="error")
    with patch("clawdia.relay.tunnel.subprocess.run", return_value=mock_result):
        assert tunnel_exists("broken") is None


def test_tunnel_exists_timeout():
    with patch("clawdia.relay.tunnel.subprocess.run", side_effect=TimeoutError):
        assert tunnel_exists("slow") is None


# ---------------------------------------------------------------------------
# generate_tunnel_config
# ---------------------------------------------------------------------------

def test_generate_tunnel_config(tmp_path):
    creds = Path("/home/user/.cloudflared/abc-123.json")
    path = generate_tunnel_config(
        data_dir=tmp_path,
        tunnel_uuid="abc-123",
        credentials_file=creds,
        hostname="relay.example.com",
        port=8765,
    )

    assert path.exists()
    content = path.read_text()
    assert "tunnel: abc-123" in content
    assert f"credentials-file: {creds}" in content
    assert "hostname: relay.example.com" in content
    assert "service: http://localhost:8765" in content
    assert "service: http_status:404" in content


def test_generate_tunnel_config_creates_dir(tmp_path):
    subdir = tmp_path / "nested" / "data"
    generate_tunnel_config(
        data_dir=subdir,
        tunnel_uuid="x",
        credentials_file=Path("/creds.json"),
        hostname="test.example.com",
        port=9999,
    )
    assert subdir.exists()
    assert (subdir / "cloudflared-config.yml").exists()


# ---------------------------------------------------------------------------
# get_tunnel_url
# ---------------------------------------------------------------------------

def test_get_tunnel_url_configured():
    config = Config()
    config.tunnel_hostname = "relay.example.com"
    assert get_tunnel_url(config) == "wss://relay.example.com"


def test_get_tunnel_url_not_configured():
    config = Config()
    assert get_tunnel_url(config) is None


def test_get_tunnel_url_empty_hostname():
    config = Config()
    config.tunnel_hostname = ""
    assert get_tunnel_url(config) is None


# ---------------------------------------------------------------------------
# _find_credentials_file
# ---------------------------------------------------------------------------

def test_find_credentials_file_exact(tmp_path):
    creds = tmp_path / "abc-123.json"
    creds.touch()
    with patch("clawdia.relay.tunnel._DEFAULT_CREDENTIALS_DIR", tmp_path):
        result = _find_credentials_file("abc-123")
    assert result == creds


def test_find_credentials_file_missing(tmp_path):
    with patch("clawdia.relay.tunnel._DEFAULT_CREDENTIALS_DIR", tmp_path):
        result = _find_credentials_file("nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# start_named_tunnel
# ---------------------------------------------------------------------------

def test_start_named_tunnel_writes_pid(tmp_path):
    config = Config()
    config.tunnel_uuid = "abc-123"
    config.tunnel_hostname = "relay.example.com"
    config.relay_port = 8765

    creds = tmp_path / "creds" / "abc-123.json"
    creds.parent.mkdir()
    creds.touch()

    mock_proc = MagicMock()
    mock_proc.pid = 42

    with (
        patch("clawdia.relay.tunnel._DEFAULT_CREDENTIALS_DIR", creds.parent),
        patch("clawdia.relay.tunnel.subprocess.Popen", return_value=mock_proc),
        patch("clawdia.relay.tunnel._pid_alive", return_value=True),
        patch("clawdia.relay.tunnel.time.sleep"),
    ):
        pid = start_named_tunnel(tmp_path, "clawdia-relay", config)

    assert pid == 42
    # Verify config YAML was generated
    assert (tmp_path / "cloudflared-config.yml").exists()


def test_start_named_tunnel_no_uuid_raises():
    config = Config()
    config.tunnel_hostname = "relay.example.com"
    # tunnel_uuid is None

    with pytest.raises(RuntimeError, match="missing uuid or hostname"):
        start_named_tunnel(Path("/tmp"), "test", config)


def test_start_named_tunnel_no_creds_raises(tmp_path):
    config = Config()
    config.tunnel_uuid = "abc-123"
    config.tunnel_hostname = "relay.example.com"

    with (
        patch("clawdia.relay.tunnel._DEFAULT_CREDENTIALS_DIR", tmp_path),
        pytest.raises(RuntimeError, match="Credentials file"),
    ):
        start_named_tunnel(tmp_path, "test", config)


# ---------------------------------------------------------------------------
# stop_named_tunnel
# ---------------------------------------------------------------------------

def test_stop_named_tunnel_not_running():
    with patch("clawdia.relay.tunnel._pid_alive", return_value=False):
        assert stop_named_tunnel(99999) is True


def test_stop_named_tunnel_sends_sigterm():
    with (
        patch("clawdia.relay.tunnel._pid_alive", side_effect=[True, True, False]),
        patch("clawdia.relay.tunnel.os.kill") as mock_kill,
        patch("clawdia.relay.tunnel.time.sleep"),
    ):
        result = stop_named_tunnel(123)

    assert result is True
    mock_kill.assert_called_once_with(123, __import__("signal").SIGTERM)


# ---------------------------------------------------------------------------
# ensure_tunnel
# ---------------------------------------------------------------------------

def test_ensure_tunnel_not_configured():
    config = Config()  # no tunnel fields set
    info = {"pid": 1, "port": 8765, "token": "x"}
    result = ensure_tunnel(Path("/tmp"), config, info)
    assert result is None
    assert "tunnel_pid" not in info


def test_ensure_tunnel_already_running():
    config = Config()
    config.tunnel_name = "clawdia-relay"
    config.tunnel_hostname = "relay.example.com"

    info = {"pid": 1, "port": 8765, "token": "x", "tunnel_pid": 42}
    with patch("clawdia.relay.tunnel._pid_alive", return_value=True):
        result = ensure_tunnel(Path("/tmp"), config, info)

    assert result == "wss://relay.example.com"
    assert info["tunnel_pid"] == 42  # unchanged


def test_ensure_tunnel_starts_new(tmp_path):
    config = Config()
    config.tunnel_name = "clawdia-relay"
    config.tunnel_uuid = "abc-123"
    config.tunnel_hostname = "relay.example.com"
    config.relay_port = 8765

    creds = tmp_path / "creds" / "abc-123.json"
    creds.parent.mkdir()
    creds.touch()

    info = {"pid": 1, "port": 8765, "token": "x"}

    mock_proc = MagicMock()
    mock_proc.pid = 99

    with (
        patch("clawdia.relay.tunnel._DEFAULT_CREDENTIALS_DIR", creds.parent),
        patch("clawdia.relay.tunnel.subprocess.Popen", return_value=mock_proc),
        patch("clawdia.relay.tunnel._pid_alive", return_value=True),
        patch("clawdia.relay.tunnel.time.sleep"),
    ):
        result = ensure_tunnel(tmp_path, config, info)

    assert result == "wss://relay.example.com"
    assert info["tunnel_pid"] == 99


# ---------------------------------------------------------------------------
# start_quick_tunnel
# ---------------------------------------------------------------------------

def test_start_quick_tunnel_success(tmp_path):
    mock_proc = MagicMock()
    mock_proc.pid = 55

    call_count = 0

    def fake_sleep(_):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            # Write the URL to the log file after a couple of polls
            log = tmp_path / "quick_tunnel.log"
            log.write_text(
                "2024-01-01 INFO Starting tunnel\n"
                "2024-01-01 INFO +-------------------------------------------+\n"
                "2024-01-01 INFO | https://foo-bar-baz.trycloudflare.com     |\n"
                "2024-01-01 INFO +-------------------------------------------+\n"
            )

    with (
        patch("clawdia.relay.tunnel.subprocess.Popen", return_value=mock_proc),
        patch("clawdia.relay.tunnel._pid_alive", return_value=True),
        patch("clawdia.relay.tunnel.time.sleep", side_effect=fake_sleep),
        patch("clawdia.relay.tunnel.time.monotonic", side_effect=[0, 0.3, 0.6, 0.9]),
    ):
        pid, url = start_quick_tunnel(tmp_path, 8765)

    assert pid == 55
    assert url == "wss://foo-bar-baz.trycloudflare.com"


def test_start_quick_tunnel_process_exits(tmp_path):
    mock_proc = MagicMock()
    mock_proc.pid = 56

    with (
        patch("clawdia.relay.tunnel.subprocess.Popen", return_value=mock_proc),
        patch("clawdia.relay.tunnel._pid_alive", return_value=False),
        patch("clawdia.relay.tunnel.time.sleep"),
        patch("clawdia.relay.tunnel.time.monotonic", side_effect=[0, 0.3]),
        pytest.raises(RuntimeError, match="exited immediately"),
    ):
        start_quick_tunnel(tmp_path, 8765)


def test_start_quick_tunnel_timeout(tmp_path):
    mock_proc = MagicMock()
    mock_proc.pid = 57

    with (
        patch("clawdia.relay.tunnel.subprocess.Popen", return_value=mock_proc),
        patch("clawdia.relay.tunnel._pid_alive", return_value=True),
        patch("clawdia.relay.tunnel.time.sleep"),
        # Simulate time advancing past the 15s deadline
        patch("clawdia.relay.tunnel.time.monotonic", side_effect=[0, 16]),
        pytest.raises(RuntimeError, match="Timed out"),
    ):
        start_quick_tunnel(tmp_path, 8765)


# ---------------------------------------------------------------------------
# stop_quick_tunnel
# ---------------------------------------------------------------------------

def test_stop_quick_tunnel_not_running():
    with patch("clawdia.relay.tunnel._pid_alive", return_value=False):
        assert stop_quick_tunnel(99999) is True


def test_stop_quick_tunnel_sends_sigterm():
    with (
        patch("clawdia.relay.tunnel._pid_alive", side_effect=[True, True, False]),
        patch("clawdia.relay.tunnel.os.kill") as mock_kill,
        patch("clawdia.relay.tunnel.time.sleep"),
    ):
        result = stop_quick_tunnel(123)

    assert result is True
    mock_kill.assert_called_once_with(123, signal.SIGTERM)


# ---------------------------------------------------------------------------
# ensure_quick_tunnel
# ---------------------------------------------------------------------------

def test_ensure_quick_tunnel_no_cloudflared():
    with patch("clawdia.relay.tunnel.has_cloudflared", return_value=False):
        result = ensure_quick_tunnel(Path("/tmp/data"), 8765)
    assert result is None


def test_ensure_quick_tunnel_reuses_existing(tmp_path):
    # Write daemon info with an existing quick tunnel
    info = {"pid": 1, "port": 8765, "token": "x",
            "quick_tunnel_pid": 42, "quick_tunnel_url": "wss://existing.trycloudflare.com"}
    info_path = tmp_path / "relay_daemon.json"
    info_path.write_text(json.dumps(info))

    with (
        patch("clawdia.relay.tunnel.has_cloudflared", return_value=True),
        patch("clawdia.relay.tunnel._pid_alive", return_value=True),
    ):
        result = ensure_quick_tunnel(tmp_path, 8765)

    assert result == (42, "wss://existing.trycloudflare.com")


def test_ensure_quick_tunnel_starts_new(tmp_path):
    # Write daemon info without quick tunnel
    info = {"pid": 1, "port": 8765, "token": "x"}
    info_path = tmp_path / "relay_daemon.json"
    info_path.write_text(json.dumps(info))

    with (
        patch("clawdia.relay.tunnel.has_cloudflared", return_value=True),
        patch("clawdia.relay.tunnel.start_quick_tunnel", return_value=(77, "wss://new.trycloudflare.com")) as mock_start,
    ):
        result = ensure_quick_tunnel(tmp_path, 8765)

    assert result == (77, "wss://new.trycloudflare.com")
    mock_start.assert_called_once_with(tmp_path, 8765)

    # Verify daemon info was updated
    updated_info = json.loads(info_path.read_text())
    assert updated_info["quick_tunnel_pid"] == 77
    assert updated_info["quick_tunnel_url"] == "wss://new.trycloudflare.com"


def test_ensure_quick_tunnel_replaces_dead(tmp_path):
    # Write daemon info with dead quick tunnel
    info = {"pid": 1, "port": 8765, "token": "x",
            "quick_tunnel_pid": 42, "quick_tunnel_url": "wss://dead.trycloudflare.com"}
    info_path = tmp_path / "relay_daemon.json"
    info_path.write_text(json.dumps(info))

    with (
        patch("clawdia.relay.tunnel.has_cloudflared", return_value=True),
        patch("clawdia.relay.tunnel._pid_alive", return_value=False),
        patch("clawdia.relay.tunnel.start_quick_tunnel", return_value=(88, "wss://fresh.trycloudflare.com")),
    ):
        result = ensure_quick_tunnel(tmp_path, 8765)

    assert result == (88, "wss://fresh.trycloudflare.com")
    updated_info = json.loads(info_path.read_text())
    assert updated_info["quick_tunnel_pid"] == 88
    assert updated_info["quick_tunnel_url"] == "wss://fresh.trycloudflare.com"


def test_ensure_quick_tunnel_start_failure(tmp_path):
    info = {"pid": 1, "port": 8765, "token": "x"}
    info_path = tmp_path / "relay_daemon.json"
    info_path.write_text(json.dumps(info))

    with (
        patch("clawdia.relay.tunnel.has_cloudflared", return_value=True),
        patch("clawdia.relay.tunnel.start_quick_tunnel", side_effect=RuntimeError("boom")),
    ):
        result = ensure_quick_tunnel(tmp_path, 8765)

    assert result is None
