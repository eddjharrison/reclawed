"""Tests for named Cloudflare tunnel management."""

import json
import os
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
