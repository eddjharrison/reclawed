"""Group chat flow — Create Group and Join Group modal screens."""

from __future__ import annotations

import socket
import subprocess
import uuid
from urllib.parse import parse_qs, urlparse

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


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

    def __init__(self, port: int = 8765) -> None:
        super().__init__()
        self._port = port
        self._room_id: str = str(uuid.uuid4())
        self._token: str = str(uuid.uuid4()).replace("-", "")[:16]
        self._participant_id: str = str(uuid.uuid4())
        self._relay_server = None  # asyncio.Server handle
        self._conn_string: str = ""

    def compose(self) -> ComposeResult:
        hostname = self._get_hostname()
        self._conn_string = (
            f"ws://{hostname}:{self._port}/room/{self._room_id}?token={self._token}"
        )
        with Vertical():
            yield Label("Create Group Chat", id="title")
            yield Label(
                "Starting relay server...",
                id="status",
            )
            yield Label("Share this connection string with participants:", id="conn-string-label")
            yield Static(self._conn_string, id="conn-string")
            yield Label(
                "Note: Remote participants need your public IP / port forwarding.\n"
                "Replace the hostname above with your public IP if needed.",
                id="hint",
            )
            with Horizontal():
                yield Button("Copy", id="btn-copy", variant="default")
                yield Button("Start Chat", id="btn-start", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="error")

    async def on_mount(self) -> None:
        """Start the embedded relay server once the screen is visible."""
        status = self.query_one("#status", Label)
        try:
            from reclawed.relay.embedded import start_embedded_relay
            self._relay_server = await start_embedded_relay(
                port=self._port,
                token=self._token,
            )
            status.update("Relay server running.")
        except Exception as exc:
            status.update(f"Failed to start relay: {exc}")
            self.query_one("#btn-start", Button).disabled = True

    @staticmethod
    def _get_hostname() -> str:
        """Return the LAN hostname for use in connection strings."""
        try:
            # Attempt to get the LAN-routable IP by opening a throwaway socket.
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return socket.gethostname()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-copy":
            self._copy_to_clipboard(self._conn_string)
        elif event.button.id == "btn-start":
            self.dismiss({
                "room_id": self._room_id,
                "relay_url": f"ws://127.0.0.1:{self._port}",
                "token": self._token,
                "port": self._port,
                "participant_id": self._participant_id,
                "relay_server": self._relay_server,
            })
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def action_cancel(self) -> None:
        # Shut down the relay server if it was started but we're cancelling.
        if self._relay_server is not None:
            self._relay_server.close()
        self.dismiss(None)

    @staticmethod
    def _copy_to_clipboard(text: str) -> None:
        """Best-effort clipboard copy: pbcopy (macOS), then xclip (Linux)."""
        try:
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
            return
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode(),
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass


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
        """Parse a ws:// connection string into component parts.

        Expected format::

            ws://<host>:<port>/room/<room_id>?token=<token>

        Returns a dict with keys: relay_url, room_id, token, participant_id.
        Returns None on parse failure.
        """
        try:
            parsed = urlparse(raw)
            if parsed.scheme not in ("ws", "wss"):
                return None

            host = parsed.hostname
            port = parsed.port
            if not host or not port:
                return None

            # Extract room_id from path: /room/<room_id>
            path_parts = [p for p in parsed.path.split("/") if p]
            if len(path_parts) < 2 or path_parts[0] != "room":
                return None
            room_id = path_parts[1]

            params = parse_qs(parsed.query)
            token = (params.get("token") or [""])[0] or None

            relay_url = f"{parsed.scheme}://{host}:{port}"

            return {
                "room_id": room_id,
                "relay_url": relay_url,
                "token": token,
                "participant_id": str(uuid.uuid4()),
            }
        except Exception:
            return None

    def action_cancel(self) -> None:
        self.dismiss(None)
