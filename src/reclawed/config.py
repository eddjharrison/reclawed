"""Configuration for Re:Clawed."""

from __future__ import annotations

import os
import platform
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# Valid theme names and their mapping to Textual built-in theme identifiers.
THEME_MAP: dict[str, str] = {
    "dark": "textual-dark",
    "light": "textual-light",
    "dracula": "dracula",
    "monokai": "monokai",
}

# Ordered list used for cycling (Ctrl+T).
THEME_CYCLE: list[str] = list(THEME_MAP.keys())

# Palette of Rich color names cycled across workspaces (index-based assignment).
WORKSPACE_COLOR_PALETTE: list[str] = ["cyan", "yellow", "green", "magenta", "blue", "red"]


@dataclass
class Workspace:
    """A named project directory for grouping sessions."""

    name: str
    path: str
    color: str = ""
    # Optional per-workspace overrides — None means inherit from global config.
    model: str | None = None
    permission_mode: str | None = None
    allowed_tools: str | None = None

    @property
    def expanded_path(self) -> str:
        """Return the path with ~ expanded to the user's home directory."""
        return str(Path(self.path).expanduser().resolve())


def _default_data_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "reclawed"
    elif system == "Windows":
        return Path.home() / "AppData" / "Local" / "reclawed"
    else:
        return Path.home() / ".local" / "share" / "reclawed"


def _config_file_path() -> Path:
    """Return the canonical config file location, varying by platform.

    - macOS:   ~/Library/Application Support/reclawed/config.toml
    - Windows: %APPDATA%/reclawed/config.toml  (falls back to ~/AppData/Roaming)
    - Linux:   ~/.config/reclawed/config.toml  (respects $XDG_CONFIG_HOME)
    """
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "reclawed" / "config.toml"
    elif system == "Windows":
        import os
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "reclawed" / "config.toml"
    else:
        import os
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
        return base / "reclawed" / "config.toml"


@dataclass
class Config:
    data_dir: Path = field(default_factory=_default_data_dir)
    claude_binary: str = "claude"
    stream_throttle_ms: int = 50
    max_quote_length: int = 200
    theme: str = "dark"
    participant_name: str = "User"
    relay_port: int = 8765
    # Group chat auto-respond mode (runtime default; also loadable from TOML).
    # "own"      — Claude responds only to your own messages (default)
    # "mentions" — Claude responds when @mentioned in a remote message
    # "all"      — Claude responds to every human message in the room
    # "off"      — Claude never responds automatically
    group_auto_respond: str = "own"
    group_context_mode: str = "isolated"  # "isolated" | "shared_history"
    group_context_window: int = 20  # number of recent messages to include as context
    # Agent SDK settings
    permission_mode: str = "acceptEdits"  # "default" | "acceptEdits" | "bypassPermissions"
    allowed_tools: str = "Read,Edit,Bash,Glob,Grep,Write"  # comma-separated tool list
    # Auto-name sessions using Claude after the first exchange
    auto_name_sessions: bool = False
    # Workspaces — multi-project session grouping
    workspaces: list[Workspace] = field(default_factory=list)
    # Relay daemon settings
    relay_mode: str = "local"  # "local" (TUI manages daemon) | "remote" (external server)
    relay_url: str | None = None  # remote mode: "wss://relay.company.com"
    relay_token: str | None = None  # remote mode: shared server token

    def __post_init__(self) -> None:
        # Normalise theme to a known key; fall back to "dark" for unknown values.
        if self.theme not in THEME_MAP:
            self.theme = "dark"
        # Normalise group_auto_respond; fall back to "own" for unknown values.
        if self.group_auto_respond not in {"own", "mentions", "all", "off"}:
            self.group_auto_respond = "own"
        if self.group_context_mode not in {"isolated", "shared_history"}:
            self.group_context_mode = "isolated"
        if self.relay_mode not in {"local", "remote"}:
            self.relay_mode = "local"
        # Auto-assign palette colors to workspaces that have none set.
        for idx, ws in enumerate(self.workspaces):
            if not ws.color:
                ws.color = WORKSPACE_COLOR_PALETTE[idx % len(WORKSPACE_COLOR_PALETTE)]

    @property
    def db_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "history.db"

    @property
    def textual_theme(self) -> str:
        """Return the Textual theme name for the current theme setting."""
        return THEME_MAP.get(self.theme, "textual-dark")

    def workspace_for_cwd(self, cwd: str | None) -> Workspace | None:
        """Return the workspace whose expanded_path matches *cwd*, or None."""
        if not cwd or not self.workspaces:
            return None
        resolved = str(Path(cwd).expanduser().resolve())
        for ws in self.workspaces:
            if ws.expanded_path == resolved:
                return ws
        return None

    def save(self, config_path: Path | None = None) -> None:
        """Write config to a TOML file.

        Parameters
        ----------
        config_path:
            Override the default config file location.  Useful in tests.
        """
        path = config_path or _config_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []

        def _toml_str(value: str) -> str:
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

        # Scalar fields
        lines.append(f"data_dir = {_toml_str(str(self.data_dir))}")
        lines.append(f"claude_binary = {_toml_str(self.claude_binary)}")
        lines.append(f"stream_throttle_ms = {self.stream_throttle_ms}")
        lines.append(f"max_quote_length = {self.max_quote_length}")
        lines.append(f"theme = {_toml_str(self.theme)}")
        lines.append(f"participant_name = {_toml_str(self.participant_name)}")
        lines.append(f"relay_port = {self.relay_port}")
        lines.append(f"group_auto_respond = {_toml_str(self.group_auto_respond)}")
        lines.append(f"group_context_mode = {_toml_str(self.group_context_mode)}")
        lines.append(f"group_context_window = {self.group_context_window}")
        lines.append(f"permission_mode = {_toml_str(self.permission_mode)}")
        lines.append(f"allowed_tools = {_toml_str(self.allowed_tools)}")
        lines.append(f"auto_name_sessions = {'true' if self.auto_name_sessions else 'false'}")
        lines.append(f"relay_mode = {_toml_str(self.relay_mode)}")
        if self.relay_url:
            lines.append(f"relay_url = {_toml_str(self.relay_url)}")
        if self.relay_token:
            lines.append(f"relay_token = {_toml_str(self.relay_token)}")

        # Workspaces
        for ws in self.workspaces:
            lines.append("")
            lines.append("[[workspaces]]")
            lines.append(f"name = {_toml_str(ws.name)}")
            lines.append(f"path = {_toml_str(ws.path)}")
            lines.append(f"color = {_toml_str(ws.color)}")
            if ws.model is not None:
                lines.append(f"model = {_toml_str(ws.model)}")
            if ws.permission_mode is not None:
                lines.append(f"permission_mode = {_toml_str(ws.permission_mode)}")
            if ws.allowed_tools is not None:
                lines.append(f"allowed_tools = {_toml_str(ws.allowed_tools)}")

        lines.append("")  # trailing newline

        # Atomic write: temp file then rename
        fd, tmp = tempfile.mkstemp(
            dir=path.parent, suffix=".toml.tmp", prefix=".reclawed-"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @classmethod
    def load(cls, config_path: Path | None = None) -> "Config":
        """Load config from a TOML file, falling back to defaults if absent.

        Parameters
        ----------
        config_path:
            Override the default config file location.  Useful in tests.
        """
        path = config_path or _config_file_path()
        if not path.exists():
            return cls()

        with path.open("rb") as fh:
            raw = tomllib.load(fh)

        kwargs: dict[str, object] = {}

        if "data_dir" in raw:
            kwargs["data_dir"] = Path(str(raw["data_dir"]))
        if "claude_binary" in raw:
            kwargs["claude_binary"] = str(raw["claude_binary"])
        if "stream_throttle_ms" in raw:
            kwargs["stream_throttle_ms"] = int(raw["stream_throttle_ms"])  # type: ignore[arg-type]
        if "max_quote_length" in raw:
            kwargs["max_quote_length"] = int(raw["max_quote_length"])  # type: ignore[arg-type]
        if "theme" in raw:
            kwargs["theme"] = str(raw["theme"])
        if "participant_name" in raw:
            kwargs["participant_name"] = str(raw["participant_name"])
        if "relay_port" in raw:
            kwargs["relay_port"] = int(raw["relay_port"])  # type: ignore[arg-type]
        if "group_auto_respond" in raw:
            kwargs["group_auto_respond"] = str(raw["group_auto_respond"])
        if "group_context_mode" in raw:
            kwargs["group_context_mode"] = str(raw["group_context_mode"])
        if "group_context_window" in raw:
            kwargs["group_context_window"] = int(raw["group_context_window"])  # type: ignore[arg-type]
        if "permission_mode" in raw:
            kwargs["permission_mode"] = str(raw["permission_mode"])
        if "allowed_tools" in raw:
            kwargs["allowed_tools"] = str(raw["allowed_tools"])
        if "auto_name_sessions" in raw:
            kwargs["auto_name_sessions"] = bool(raw["auto_name_sessions"])
        if "relay_mode" in raw:
            kwargs["relay_mode"] = str(raw["relay_mode"])
        if "relay_url" in raw:
            kwargs["relay_url"] = str(raw["relay_url"])
        if "relay_token" in raw:
            kwargs["relay_token"] = str(raw["relay_token"])

        # Parse [[workspaces]] array
        if "workspaces" in raw and isinstance(raw["workspaces"], list):
            workspaces = []
            for w in raw["workspaces"]:
                if "name" not in w or "path" not in w:
                    continue
                workspaces.append(Workspace(
                    name=str(w["name"]),
                    path=str(w["path"]),
                    color=str(w.get("color", "")),
                    model=str(w["model"]) if "model" in w else None,
                    permission_mode=str(w["permission_mode"]) if "permission_mode" in w else None,
                    allowed_tools=str(w["allowed_tools"]) if "allowed_tools" in w else None,
                ))
            kwargs["workspaces"] = workspaces

        return cls(**kwargs)  # type: ignore[arg-type]
