"""Configuration for Re:Clawed."""

from __future__ import annotations

import platform
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


def _default_data_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "reclawed"
    elif system == "Windows":
        return Path.home() / "AppData" / "Local" / "reclawed"
    else:
        return Path.home() / ".local" / "share" / "reclawed"


def _config_file_path() -> Path:
    """Return the canonical config file location (~/.config/reclawed/config.toml)."""
    return Path.home() / ".config" / "reclawed" / "config.toml"


@dataclass
class Config:
    data_dir: Path = field(default_factory=_default_data_dir)
    claude_binary: str = "claude"
    stream_throttle_ms: int = 50
    max_quote_length: int = 200
    theme: str = "dark"
    participant_name: str = "User"
    relay_port: int = 8765

    def __post_init__(self) -> None:
        # Normalise theme to a known key; fall back to "dark" for unknown values.
        if self.theme not in THEME_MAP:
            self.theme = "dark"

    @property
    def db_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "history.db"

    @property
    def textual_theme(self) -> str:
        """Return the Textual theme name for the current theme setting."""
        return THEME_MAP.get(self.theme, "textual-dark")

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

        return cls(**kwargs)  # type: ignore[arg-type]
