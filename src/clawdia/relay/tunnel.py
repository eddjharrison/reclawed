"""Cloudflare tunnel management — named and quick tunnels.

Named tunnels require a Cloudflare account and domain on Cloudflare DNS.
Quick tunnels use ``cloudflared tunnel --url`` for automatic NAT traversal
with a random ``trycloudflare.com`` URL.

Both tunnel types are daemonized (detached subprocess, PID persisted in
``relay_daemon.json``) so they survive TUI quit/restart.

Setup flow for named tunnels (one-time):
    clawdia tunnel setup relay.yourdomain.com

Quick tunnels are started automatically when creating a group chat.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_CLOUDFLARED_CONFIG_FILE = "cloudflared-config.yml"
_DEFAULT_CREDENTIALS_DIR = Path.home() / ".cloudflared"


def has_cloudflared() -> bool:
    """Check if cloudflared is on PATH."""
    return shutil.which("cloudflared") is not None


def is_logged_in() -> bool:
    """Check if the user has authenticated with Cloudflare.

    ``cloudflared tunnel login`` saves a certificate to
    ``~/.cloudflared/cert.pem``.
    """
    return (_DEFAULT_CREDENTIALS_DIR / "cert.pem").exists()


def tunnel_exists(tunnel_name: str) -> str | None:
    """Check if a named tunnel exists.  Returns the tunnel UUID or None."""
    try:
        result = subprocess.run(
            ["cloudflared", "tunnel", "list", "--name", tunnel_name, "--output", "json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None
        tunnels = json.loads(result.stdout)
        if isinstance(tunnels, list) and tunnels:
            return str(tunnels[0]["id"])
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, OSError):
        return None


def create_tunnel(tunnel_name: str) -> tuple[str, Path]:
    """Create a named tunnel.  Returns (uuid, credentials_file_path).

    Raises ``RuntimeError`` on failure.
    """
    result = subprocess.run(
        ["cloudflared", "tunnel", "create", tunnel_name],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to create tunnel '{tunnel_name}': {result.stderr.strip()}"
        )

    # Parse UUID from output.  cloudflared prints:
    #   Created tunnel <name> with id <uuid>
    output = result.stdout + result.stderr  # some versions print to stderr
    for line in output.splitlines():
        if "with id" in line.lower():
            parts = line.strip().split()
            uuid = parts[-1]
            creds = _DEFAULT_CREDENTIALS_DIR / f"{uuid}.json"
            if creds.exists():
                return uuid, creds
            # Credentials file may not match exact path — search for it
            for f in _DEFAULT_CREDENTIALS_DIR.glob("*.json"):
                if uuid in f.name:
                    return uuid, f
            return uuid, creds

    raise RuntimeError(
        f"Could not parse tunnel UUID from cloudflared output:\n{output}"
    )


def route_dns(tunnel_name: str, hostname: str) -> None:
    """Create a DNS CNAME routing *hostname* to the named tunnel.

    Raises ``RuntimeError`` on failure.
    """
    result = subprocess.run(
        ["cloudflared", "tunnel", "route", "dns", "--overwrite-dns", tunnel_name, hostname],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to route DNS for '{hostname}': {result.stderr.strip()}"
        )


def delete_tunnel(tunnel_name: str) -> None:
    """Delete a named tunnel.

    Raises ``RuntimeError`` on failure.
    """
    result = subprocess.run(
        ["cloudflared", "tunnel", "delete", tunnel_name],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to delete tunnel '{tunnel_name}': {result.stderr.strip()}"
        )


def generate_tunnel_config(
    data_dir: Path,
    tunnel_uuid: str,
    credentials_file: Path,
    hostname: str,
    port: int,
) -> Path:
    """Write a cloudflared config YAML for the named tunnel.

    Returns the path to the generated config file.
    """
    config_path = data_dir / _CLOUDFLARED_CONFIG_FILE
    data_dir.mkdir(parents=True, exist_ok=True)

    content = (
        f"tunnel: {tunnel_uuid}\n"
        f"credentials-file: {credentials_file}\n"
        f"\n"
        f"ingress:\n"
        f"  - hostname: {hostname}\n"
        f"    service: http://localhost:{port}\n"
        f"  - service: http_status:404\n"
    )
    config_path.write_text(content, encoding="utf-8")
    logger.info("Wrote cloudflared config to %s", config_path)
    return config_path


def _find_credentials_file(tunnel_uuid: str) -> Path | None:
    """Locate the credentials JSON for a tunnel UUID."""
    expected = _DEFAULT_CREDENTIALS_DIR / f"{tunnel_uuid}.json"
    if expected.exists():
        return expected
    # Fallback: search for any file containing the UUID
    for f in _DEFAULT_CREDENTIALS_DIR.glob("*.json"):
        if tunnel_uuid in f.name:
            return f
    return None


def get_tunnel_url(config) -> str | None:
    """Return the stable WSS URL if a named tunnel is configured, else None.

    Parameters
    ----------
    config:
        A Config instance (imported here to avoid circular imports).
    """
    hostname = getattr(config, "tunnel_hostname", None)
    if hostname:
        return f"wss://{hostname}"
    return None


# ---------------------------------------------------------------------------
# Process management — mirrors daemon.py patterns
# ---------------------------------------------------------------------------

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def start_named_tunnel(data_dir: Path, tunnel_name: str, config) -> int:
    """Start ``cloudflared tunnel run`` as a detached subprocess.

    The tunnel PID is written to the daemon info file under ``tunnel_pid``.
    Returns the PID.
    """
    config_path = data_dir / _CLOUDFLARED_CONFIG_FILE

    # Regenerate config to reflect current port
    tunnel_uuid = getattr(config, "tunnel_uuid", None)
    hostname = getattr(config, "tunnel_hostname", None)
    port = getattr(config, "relay_port", 8765)

    if not tunnel_uuid or not hostname:
        raise RuntimeError("Named tunnel not fully configured (missing uuid or hostname)")

    creds = _find_credentials_file(tunnel_uuid)
    if creds is None:
        raise RuntimeError(
            f"Credentials file for tunnel {tunnel_uuid} not found in {_DEFAULT_CREDENTIALS_DIR}. "
            f"Re-run 'clawdia tunnel setup' to fix."
        )

    generate_tunnel_config(data_dir, tunnel_uuid, creds, hostname, port)

    log_path = data_dir / "cloudflared.log"
    log_fh = open(log_path, "a")

    cmd = ["cloudflared", "tunnel", "--config", str(config_path), "run"]

    kwargs: dict = {
        "stdout": log_fh,
        "stderr": log_fh,
    }
    if sys.platform != "win32":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )

    proc = subprocess.Popen(cmd, **kwargs)
    pid = proc.pid
    logger.info("Named tunnel '%s' started (PID %d)", tunnel_name, pid)

    # Give cloudflared a moment to start
    time.sleep(1.0)
    if not _pid_alive(pid):
        raise RuntimeError(
            f"cloudflared exited immediately. Check {log_path} for details."
        )

    return pid


def stop_named_tunnel(tunnel_pid: int) -> bool:
    """Stop the named tunnel process.  Returns True if stopped."""
    if not _pid_alive(tunnel_pid):
        return True

    try:
        os.kill(tunnel_pid, signal.SIGTERM)
    except OSError:
        return True

    for _ in range(30):
        time.sleep(0.1)
        if not _pid_alive(tunnel_pid):
            logger.info("Named tunnel stopped (PID %d)", tunnel_pid)
            return True

    # Force kill
    logger.warning("Tunnel PID %d didn't exit on SIGTERM, sending SIGKILL", tunnel_pid)
    try:
        os.kill(tunnel_pid, signal.SIGKILL)
    except OSError:
        pass

    for _ in range(10):
        time.sleep(0.1)
        if not _pid_alive(tunnel_pid):
            return True

    logger.error("Failed to kill tunnel PID %d", tunnel_pid)
    return False


def ensure_tunnel(data_dir: Path, config, daemon_info: dict) -> str | None:
    """Ensure the named tunnel is running if configured.

    Updates *daemon_info* in place with ``tunnel_pid`` if the tunnel
    is started.  Returns the WSS URL or None.
    """
    url = get_tunnel_url(config)
    if url is None:
        return None

    tunnel_name = getattr(config, "tunnel_name", None)
    if not tunnel_name:
        return None

    # Already running?
    existing_pid = daemon_info.get("tunnel_pid")
    if existing_pid and _pid_alive(existing_pid):
        return url

    # Start it
    pid = start_named_tunnel(data_dir, tunnel_name, config)
    daemon_info["tunnel_pid"] = pid
    return url


# ---------------------------------------------------------------------------
# Quick tunnel management — daemonized quick tunnels for group chat
# ---------------------------------------------------------------------------

_QUICK_TUNNEL_LOG = "quick_tunnel.log"
_QUICK_TUNNEL_URL_RE = re.compile(r'https?://[^\s|]*trycloudflare\.com[^\s|]*')


def start_quick_tunnel(data_dir: Path, port: int) -> tuple[int, str]:
    """Start a quick cloudflare tunnel as a detached subprocess.

    Returns ``(pid, wss_url)``.  Raises ``RuntimeError`` on failure.
    """
    log_path = data_dir / _QUICK_TUNNEL_LOG
    data_dir.mkdir(parents=True, exist_ok=True)
    # Write mode so we only parse fresh output from this process
    log_fh = open(log_path, "w")

    cmd = ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"]

    kwargs: dict = {
        "stdout": log_fh,
        "stderr": log_fh,
    }
    if sys.platform != "win32":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )

    proc = subprocess.Popen(cmd, **kwargs)
    pid = proc.pid
    logger.info("Quick tunnel started (PID %d) for port %d", pid, port)

    # Poll the log file for the trycloudflare URL
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        time.sleep(0.3)
        if not _pid_alive(pid):
            raise RuntimeError(
                f"cloudflared exited immediately. Check {log_path} for details."
            )
        try:
            content = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = _QUICK_TUNNEL_URL_RE.search(content)
        if match:
            url = match.group(0).rstrip(".| ")
            wss_url = url.replace("https://", "wss://").replace("http://", "ws://")
            logger.info("Quick tunnel URL: %s (PID %d)", wss_url, pid)
            return pid, wss_url

    raise RuntimeError(
        f"Timed out waiting for quick tunnel URL. Check {log_path} for details."
    )


def stop_quick_tunnel(tunnel_pid: int) -> bool:
    """Stop a quick tunnel process.  Returns True if stopped."""
    if not _pid_alive(tunnel_pid):
        return True

    try:
        os.kill(tunnel_pid, signal.SIGTERM)
    except OSError:
        return True

    for _ in range(30):
        time.sleep(0.1)
        if not _pid_alive(tunnel_pid):
            logger.info("Quick tunnel stopped (PID %d)", tunnel_pid)
            return True

    # Force kill
    logger.warning("Quick tunnel PID %d didn't exit on SIGTERM, sending SIGKILL", tunnel_pid)
    try:
        os.kill(tunnel_pid, signal.SIGKILL)
    except OSError:
        pass

    for _ in range(10):
        time.sleep(0.1)
        if not _pid_alive(tunnel_pid):
            return True

    logger.error("Failed to kill quick tunnel PID %d", tunnel_pid)
    return False


def ensure_quick_tunnel(data_dir: Path, port: int) -> tuple[int, str] | None:
    """Ensure a quick cloudflare tunnel is running.

    Reuses an existing tunnel if it's still alive; starts a new one
    otherwise.  Persists the PID and URL in ``relay_daemon.json``.

    Returns ``(pid, wss_url)`` or ``None`` if cloudflared is not installed.
    """
    if not has_cloudflared():
        return None

    from clawdia.relay.daemon import get_daemon_info, _write_daemon_info

    info = get_daemon_info(data_dir) or {}

    # Reuse existing tunnel if still alive
    qt_pid = info.get("quick_tunnel_pid")
    qt_url = info.get("quick_tunnel_url")
    if qt_pid and qt_url and _pid_alive(qt_pid):
        logger.info("Reusing existing quick tunnel (PID %d, URL %s)", qt_pid, qt_url)
        return qt_pid, qt_url

    # Start a new one
    try:
        pid, wss_url = start_quick_tunnel(data_dir, port)
    except (RuntimeError, FileNotFoundError, OSError) as exc:
        logger.error("Failed to start quick tunnel: %s", exc)
        return None

    # Re-read info in case another process updated it concurrently
    info = get_daemon_info(data_dir) or {}
    info["quick_tunnel_pid"] = pid
    info["quick_tunnel_url"] = wss_url
    _write_daemon_info(data_dir, info)

    return pid, wss_url
