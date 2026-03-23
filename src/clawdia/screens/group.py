"""Group chat flow — Create Group and Join Group modal screens."""

from __future__ import annotations

import asyncio
import socket
import uuid
from urllib.parse import parse_qs, urlparse

from reclawed.config import Config
from reclawed.crypto import generate_passphrase
from reclawed.relay.daemon import ensure_daemon
from reclawed.utils import copy_to_clipboard

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


async def _start_cloudflare_tunnel(port: int) -> tuple[str | None, asyncio.subprocess.Process | None]:
    """Try to start a cloudflare quick tunnel. Returns (wss_url, proc) or (None, None)."""
    import re
    import sys
    _no_win = {}
    if sys.platform == "win32":
        import subprocess as _sp
        _no_win["creationflags"] = _sp.CREATE_NO_WINDOW
    try:
        proc = await asyncio.create_subprocess_exec(
            "cloudflared", "tunnel", "--url", f"http://localhost:{port}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_no_win,
        )
        assert proc.stderr is not None
        url_pattern = re.compile(r'https?://[^\s|]*trycloudflare\.com[^\s|]*')
        try:
            async def _read_url():
                assert proc.stderr is not None
                while True:
                    line = await proc.stderr.readline()
                    if not line:
                        return None
                    text = line.decode("utf-8", errors="replace")
                    match = url_pattern.search(text)
                    if match:
                        url = match.group(0).rstrip('.| ')
                        return url.replace("https://", "wss://").replace("http://", "ws://")

            url = await asyncio.wait_for(_read_url(), timeout=15.0)
            return url, proc
        except asyncio.TimeoutError:
            return None, proc
    except FileNotFoundError:
        return None, None
    except Exception:
        return None, None


def _get_lan_hostname() -> str:
    """Return the LAN-routable IP for use in connection strings."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return socket.gethostname()


class CreateGroupScreen(ModalScreen[dict | None]):
    """Modal that spins up the embedded relay and shows the connection string.

    Returns a dict on success::

        {
            "room_id": str,
            "relay_url": str,          # ws://<host>:<port>
            "token": str,
            "port": int,
            "participant_id": str,     # UUID for this participant
        }

    Returns ``None`` if the user cancels.
    """

    DEFAULT_CSS = """
    CreateGroupScreen {
        align: center middle;
    }
    CreateGroupScreen > Vertical {
        width: 70;
        height: auto;
        padding: 2 3;
        background: $surface;
        border: tall $primary;
    }
    CreateGroupScreen #title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    CreateGroupScreen #conn-string-label {
        color: $text-muted;
        margin-top: 1;
    }
    CreateGroupScreen #conn-string {
        color: $success;
        text-style: bold;
        background: $surface-lighten-1;
        padding: 0 1;
        margin-bottom: 1;
    }
    CreateGroupScreen #hint {
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }
    CreateGroupScreen #status {
        color: $warning;
        margin-bottom: 1;
    }
    CreateGroupScreen Horizontal {
        height: auto;
        margin-top: 1;
    }
    CreateGroupScreen Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._port = config.relay_port
        self._room_id: str = str(uuid.uuid4())
        self._participant_id: str = str(uuid.uuid4())
        self._passphrase: str = generate_passphrase()
        self._tunnel_proc: asyncio.subprocess.Process | None = None
        self._tunnel_url: str | None = None
        self._conn_string: str = ""
        # Token: in local mode, comes from daemon; in remote mode, from config
        self._token: str = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Create Group Chat", id="title")
            yield Label("Starting relay server...", id="status")
            yield Label("Share this connection string with participants:", id="conn-string-label")
            yield Static("Generating...", id="conn-string")
            yield Label("", id="hint")
            with Horizontal():
                yield Button("Copy", id="btn-copy", variant="default")
                yield Button("Start Chat", id="btn-start", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="error")

    async def on_mount(self) -> None:
        """Start/connect to the relay and generate a connection string."""
        status = self.query_one("#status", Label)
        hint = self.query_one("#hint", Label)
        conn_label = self.query_one("#conn-string", Static)

        if self._config.relay_mode == "remote":
            await self._setup_remote_mode(status, hint, conn_label)
        else:
            await self._setup_local_mode(status, hint, conn_label)

    async def _setup_remote_mode(self, status, hint, conn_label) -> None:
        """Remote mode: use the configured external relay server."""
        if not self._config.relay_url:
            status.update("Error: relay_url not configured for remote mode")
            self.query_one("#btn-start", Button).disabled = True
            return

        self._token = self._config.relay_token or ""
        relay_url = self._config.relay_url.rstrip("/")
        self._conn_string = (
            f"{relay_url}/room/{self._room_id}?token={self._token}"
            f"&key={self._passphrase}"
        )
        status.update(f"Using remote relay: {relay_url}")
        hint.update("Connected to external relay server. Share the link to invite.")
        conn_label.update(self._conn_string)

    async def _setup_local_mode(self, status, hint, conn_label) -> None:
        """Local mode: ensure daemon is running, then set up tunnel."""
        # Step 1: Ensure the relay daemon is running
        try:
            daemon_info = await asyncio.to_thread(
                ensure_daemon, self._config.data_dir, self._port,
            )
            self._token = daemon_info["token"]
            status.update("Relay daemon running. Setting up tunnel...")
        except Exception as exc:
            status.update(f"Failed to start relay daemon: {exc}")
            self.query_one("#btn-start", Button).disabled = True
            return

        # Step 2: Try to start cloudflare tunnel for automatic NAT traversal
        tunnel_url, self._tunnel_proc = await _start_cloudflare_tunnel(self._port)

        if tunnel_url:
            self._tunnel_url = tunnel_url
            self._conn_string = (
                f"{tunnel_url}/room/{self._room_id}?token={self._token}"
                f"&key={self._passphrase}"
            )
            status.update("Relay daemon running with public tunnel.")
            hint.update("Public URL — anyone with this link can join, no port forwarding needed.")
        else:
            hostname = _get_lan_hostname()
            self._conn_string = (
                f"ws://{hostname}:{self._port}/room/{self._room_id}?token={self._token}"
                f"&key={self._passphrase}"
            )
            status.update("Relay daemon running (LAN only).")
            hint.update(
                "cloudflared not found — install it for automatic public tunnels:\n"
                "  brew install cloudflared\n"
                "For now, remote users need your public IP + port forwarding on "
                f"port {self._port}."
            )

        conn_label.update(self._conn_string)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-copy":
            if copy_to_clipboard(self._conn_string):
                self.notify("Copied to clipboard!", timeout=2)
            else:
                self.notify("Copy failed — no clipboard tool available", severity="error", timeout=2)
        elif event.button.id == "btn-start":
            relay_url = f"ws://127.0.0.1:{self._port}"
            if self._config.relay_mode == "remote" and self._config.relay_url:
                relay_url = self._config.relay_url
            self.dismiss({
                "room_id": self._room_id,
                "relay_url": relay_url,
                "token": self._token,
                "port": self._port,
                "participant_id": self._participant_id,
                "tunnel_proc": self._tunnel_proc,
                "conn_string": self._conn_string,
                "encryption_passphrase": self._passphrase,
            })
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def action_cancel(self) -> None:
        if self._tunnel_proc and self._tunnel_proc.returncode is None:
            self._tunnel_proc.terminate()
        # Don't stop the relay daemon — it persists for other groups
        self.dismiss(None)


class InviteToChatScreen(ModalScreen[dict | None]):
    """Modal that upgrades an existing 1:1 chat into a group by generating
    relay credentials and a connection string.

    Reuses the relay setup logic from CreateGroupScreen but doesn't create
    a new session — the caller mutates the existing session.
    """

    DEFAULT_CSS = """
    InviteToChatScreen {
        align: center middle;
    }
    InviteToChatScreen > Vertical {
        width: 70;
        height: auto;
        padding: 2 3;
        background: $surface;
        border: tall $primary;
    }
    InviteToChatScreen #title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    InviteToChatScreen #conn-string {
        color: $success;
        text-style: bold;
        background: $surface-lighten-1;
        padding: 0 1;
        margin-bottom: 1;
    }
    InviteToChatScreen #hint {
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }
    InviteToChatScreen #status {
        color: $warning;
        margin-bottom: 1;
    }
    InviteToChatScreen Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._port = config.relay_port
        self._room_id: str = str(uuid.uuid4())
        self._participant_id: str = str(uuid.uuid4())
        self._passphrase: str = generate_passphrase()
        self._tunnel_proc: asyncio.subprocess.Process | None = None
        self._conn_string: str = ""
        self._token: str = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Invite to Chat", id="title")
            yield Label("Setting up group relay...", id="status")
            yield Static("Generating...", id="conn-string")
            yield Label("", id="hint")
            with Horizontal():
                yield Button("Copy", id="btn-copy", variant="default")
                yield Button("Start Group", id="btn-start", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="error")

    async def on_mount(self) -> None:
        status = self.query_one("#status", Label)
        hint = self.query_one("#hint", Label)
        conn_label = self.query_one("#conn-string", Static)

        if self._config.relay_mode == "remote":
            if not self._config.relay_url:
                status.update("Error: relay_url not configured for remote mode")
                self.query_one("#btn-start", Button).disabled = True
                return
            self._token = self._config.relay_token or ""
            relay_url = self._config.relay_url.rstrip("/")
            self._conn_string = (
                f"{relay_url}/room/{self._room_id}?token={self._token}"
                f"&key={self._passphrase}"
            )
            status.update(f"Using remote relay: {relay_url}")
            hint.update("Share this link to invite participants.")
        else:
            try:
                daemon_info = await asyncio.to_thread(
                    ensure_daemon, self._config.data_dir, self._port,
                )
                self._token = daemon_info["token"]
                status.update("Relay ready. Setting up tunnel...")
            except Exception as exc:
                status.update(f"Failed to start relay: {exc}")
                self.query_one("#btn-start", Button).disabled = True
                return

            tunnel_url, self._tunnel_proc = await _start_cloudflare_tunnel(self._port)
            if tunnel_url:
                self._conn_string = (
                    f"{tunnel_url}/room/{self._room_id}?token={self._token}"
                    f"&key={self._passphrase}"
                )
                status.update("Ready! Share this link to invite participants.")
                hint.update("Public URL — anyone with this link can join.")
            else:
                hostname = _get_lan_hostname()
                self._conn_string = (
                    f"ws://{hostname}:{self._port}/room/{self._room_id}?token={self._token}"
                    f"&key={self._passphrase}"
                )
                status.update("Ready (LAN only).")
                hint.update("Install cloudflared for public tunnel URLs.")

        conn_label.update(self._conn_string)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-copy":
            if copy_to_clipboard(self._conn_string):
                self.notify("Copied to clipboard!", timeout=2)
            else:
                self.notify("Copy failed", severity="error", timeout=2)
        elif event.button.id == "btn-start":
            relay_url = f"ws://127.0.0.1:{self._port}"
            if self._config.relay_mode == "remote" and self._config.relay_url:
                relay_url = self._config.relay_url
            self.dismiss({
                "room_id": self._room_id,
                "relay_url": relay_url,
                "token": self._token,
                "participant_id": self._participant_id,
                "tunnel_proc": self._tunnel_proc,
                "encryption_passphrase": self._passphrase,
            })
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def action_cancel(self) -> None:
        if self._tunnel_proc and self._tunnel_proc.returncode is None:
            self._tunnel_proc.terminate()
        self.dismiss(None)


class JoinGroupScreen(ModalScreen[dict | None]):
    """Modal for entering a connection string and joining an existing group.

    Returns a dict on success::

        {
            "room_id": str,
            "relay_url": str,    # ws://<host>:<port>
            "token": str,
            "participant_id": str,
        }

    Returns ``None`` if the user cancels.
    """

    DEFAULT_CSS = """
    JoinGroupScreen {
        align: center middle;
    }
    JoinGroupScreen > Vertical {
        width: 70;
        height: auto;
        padding: 2 3;
        background: $surface;
        border: tall $primary;
    }
    JoinGroupScreen #title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    JoinGroupScreen #error {
        color: $error;
        margin-top: 1;
    }
    JoinGroupScreen Horizontal {
        height: auto;
        margin-top: 1;
    }
    JoinGroupScreen Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Join Group Chat", id="title")
            yield Input(
                placeholder="ws://192.168.1.10:8765/room/<id>?token=<token>",
                id="conn-input",
            )
            yield Label("", id="error")
            with Horizontal():
                yield Button("Join", id="btn-join", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="error")

    def on_mount(self) -> None:
        self.query_one("#conn-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-join":
            self._attempt_join()
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Allow pressing Enter in the input to trigger join."""
        self._attempt_join()

    def _attempt_join(self) -> None:
        raw = self.query_one("#conn-input", Input).value.strip()
        error_label = self.query_one("#error", Label)

        if not raw:
            error_label.update("Please paste a connection string.")
            return

        parsed = self._parse_conn_string(raw)
        if parsed is None:
            error_label.update(
                "Invalid connection string. Expected: ws://host:port/room/<id>?token=<token>"
            )
            return

        self.dismiss(parsed)

    @staticmethod
    def _parse_conn_string(raw: str) -> dict | None:
        """Parse a ws:// or wss:// connection string into component parts.

        Supported formats::

            ws://<host>:<port>/room/<room_id>?token=<token>
            wss://<host>/room/<room_id>?token=<token>  (cloudflare tunnel)

        Returns a dict with keys: relay_url, room_id, token, participant_id.
        Returns None on parse failure.
        """
        try:
            parsed = urlparse(raw)
            if parsed.scheme not in ("ws", "wss"):
                return None

            host = parsed.hostname
            if not host:
                return None

            # Extract room_id from path: /room/<room_id>
            path_parts = [p for p in parsed.path.split("/") if p]
            if len(path_parts) < 2 or path_parts[0] != "room":
                return None
            room_id = path_parts[1]

            params = parse_qs(parsed.query)
            token = (params.get("token") or [""])[0] or None
            encryption_passphrase = (params.get("key") or [""])[0] or None

            # Build relay URL — port is optional for wss:// tunnel URLs
            if parsed.port:
                relay_url = f"{parsed.scheme}://{host}:{parsed.port}"
            else:
                relay_url = f"{parsed.scheme}://{host}"

            return {
                "room_id": room_id,
                "relay_url": relay_url,
                "token": token,
                "participant_id": str(uuid.uuid4()),
                "encryption_passphrase": encryption_passphrase,
            }
        except Exception:
            return None

    def action_cancel(self) -> None:
        self.dismiss(None)
