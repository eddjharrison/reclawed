"""Daemon lifecycle manager for the relay server.

Manages the relay server as a detached background subprocess that
persists across TUI quit/restart.  State is stored in a JSON info
file so the TUI can rediscover the daemon after restarting.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_INFO_FILE = "relay_daemon.json"


def _info_path(data_dir: Path) -> Path:
    return data_dir / _INFO_FILE


def _db_path(data_dir: Path) -> Path:
    return data_dir / "relay.db"


def _log_path(data_dir: Path) -> Path:
    return data_dir / "relay.log"


def get_daemon_info(data_dir: Path) -> dict | None:
    """Read the daemon info file, or return None if it doesn't exist."""
    path = _info_path(data_dir)
    if not path.exists():
        return None
    try:
        with path.open("r") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def _write_daemon_info(data_dir: Path, info: dict) -> None:
    path = _info_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(info, fh)


def _remove_daemon_info(data_dir: Path) -> None:
    path = _info_path(data_dir)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _port_responsive(port: int, timeout: float = 1.0) -> bool:
    """Check if something is listening on the given port."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False


def is_daemon_running(data_dir: Path) -> bool:
    """Return True if the relay daemon is running and responsive."""
    info = get_daemon_info(data_dir)
    if info is None:
        return False

    pid = info.get("pid")
    port = info.get("port")
    if not pid or not port:
        _remove_daemon_info(data_dir)
        return False

    # Check PID is alive AND port is responsive
    if _pid_alive(pid) and _port_responsive(port):
        return True

    # Stale info file — clean up
    _remove_daemon_info(data_dir)
    return False


def start_daemon(
    port: int,
    token: str,
    data_dir: Path,
) -> dict:
    """Start the relay server as a detached background subprocess.

    Returns the daemon info dict ``{"pid": int, "port": int, "token": str}``.
    Raises ``RuntimeError`` if the daemon fails to start.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    db = str(_db_path(data_dir))
    log = _log_path(data_dir)

    cmd = [
        sys.executable, "-m", "clawdia.relay.server",
        "--host", "0.0.0.0",
        "--port", str(port),
        "--token", token,
        "--db", db,
        "--log-level", "INFO",
    ]

    log_fh = open(log, "a")

    kwargs: dict = {
        "stdout": log_fh,
        "stderr": log_fh,
    }
    # Fully detach from the TUI process group
    if sys.platform != "win32":
        kwargs["start_new_session"] = True
    else:
        # CREATE_NO_WINDOW prevents a visible console.
        # CREATE_NEW_PROCESS_GROUP detaches from parent's Ctrl+C.
        # Do NOT use DETACHED_PROCESS — it opens a new console on Windows.
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )

    proc = subprocess.Popen(cmd, **kwargs)
    # Detach: let the subprocess run independently so it doesn't become a zombie
    # when the parent (TUI) exits. On Unix, start_new_session already does this
    # for session isolation; we also need to avoid holding a reference.
    actual_pid = proc.pid

    info = {"pid": actual_pid, "port": port, "token": token}
    _write_daemon_info(data_dir, info)

    # Wait for the server to become responsive
    for _ in range(30):  # 3 seconds max
        time.sleep(0.1)
        if _port_responsive(port, timeout=0.5):
            logger.info("Relay daemon started (PID %d, port %d)", proc.pid, port)
            return info

    # If we get here, the daemon didn't start in time
    logger.error("Relay daemon failed to become responsive")
    raise RuntimeError(
        f"Relay daemon failed to start on port {port}. "
        f"Check {log} for details."
    )


def stop_daemon(data_dir: Path) -> bool:
    """Stop the relay daemon. Returns True if stopped (or wasn't running).

    Also stops the co-managed named tunnel process if one is running.
    The info file is preserved (only PID removed) so the token can be
    reused on next ``ensure_daemon()`` call.
    """
    info = get_daemon_info(data_dir)
    if info is None:
        return True

    # Stop named tunnel first (if running)
    tunnel_pid = info.get("tunnel_pid")
    if tunnel_pid and _pid_alive(tunnel_pid):
        from clawdia.relay.tunnel import stop_named_tunnel
        stop_named_tunnel(tunnel_pid)

    pid = info.get("pid")
    if not pid or not _pid_alive(pid):
        return True

    # Send SIGTERM for graceful shutdown
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return True

    # Reap the child to avoid zombies, then wait for exit
    for _ in range(50):
        time.sleep(0.1)
        try:
            # WNOHANG: non-blocking reap of zombie children
            result = os.waitpid(pid, os.WNOHANG)
            if result[0] != 0:
                logger.info("Relay daemon stopped (PID %d)", pid)
                return True
        except ChildProcessError:
            # Not our child — check if the process is gone
            if not _pid_alive(pid):
                logger.info("Relay daemon stopped (PID %d)", pid)
                return True
        except OSError:
            return True

    # Force kill if SIGTERM didn't work
    logger.warning("Relay daemon PID %d didn't exit on SIGTERM, sending SIGKILL", pid)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass

    # Reap after force kill
    for _ in range(20):
        time.sleep(0.1)
        try:
            os.waitpid(pid, os.WNOHANG)
            if not _pid_alive(pid):
                return True
        except (ChildProcessError, OSError):
            if not _pid_alive(pid):
                return True

    logger.error("Failed to kill relay daemon PID %d", pid)
    return False


def ensure_daemon(data_dir: Path, port: int = 8765, config=None) -> dict:
    """Ensure the relay daemon is running. Start it if not.

    On first call, generates a random token and persists it in the
    info file.  On subsequent calls (including after daemon restarts),
    the token is reused from the info file.

    When *config* has named tunnel settings (``tunnel_hostname``),
    the tunnel process is co-managed alongside the relay server.

    Returns the daemon info dict.
    """
    # Check if daemon is already running and responsive
    info = get_daemon_info(data_dir)
    if info and _pid_alive(info.get("pid", 0)) and _port_responsive(info.get("port", 0)):
        # Relay is up — ensure tunnel is also running if configured
        if config and getattr(config, "tunnel_hostname", None):
            from clawdia.relay.tunnel import ensure_tunnel
            ensure_tunnel(data_dir, config, info)
            _write_daemon_info(data_dir, info)
        return info

    # Reuse existing token if we have one from a previous run
    token: str
    if info and info.get("token"):
        token = info["token"]
    else:
        import uuid
        token = uuid.uuid4().hex[:16]

    info = start_daemon(port=port, token=token, data_dir=data_dir)

    # Co-start named tunnel if configured
    if config and getattr(config, "tunnel_hostname", None):
        from clawdia.relay.tunnel import ensure_tunnel
        ensure_tunnel(data_dir, config, info)
        _write_daemon_info(data_dir, info)

    return info
