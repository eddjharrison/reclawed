"""Configuration for Re:Clawed."""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "reclawed"
    elif system == "Windows":
        return Path.home() / "AppData" / "Local" / "reclawed"
    else:
        return Path.home() / ".local" / "share" / "reclawed"


@dataclass
class Config:
    data_dir: Path = field(default_factory=_default_data_dir)
    claude_binary: str = "claude"
    stream_throttle_ms: int = 50
    max_quote_length: int = 200

    @property
    def db_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "history.db"
