"""Text-to-speech engines — edge-tts (free), system TTS, or silent."""

from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


class BaseTTS:
    """Base class for TTS engines."""

    async def speak(self, text: str) -> None:
        """Speak the given text. Override in subclasses."""

    def cancel(self) -> None:
        """Cancel any in-progress playback. Override in subclasses."""


class EdgeTTS(BaseTTS):
    """Free Microsoft TTS via edge-tts library.

    Good quality, requires internet, no API key.
    """

    def __init__(self, voice: str = "en-US-AriaNeural"):
        self._voice = voice
        self._current_process = None

    async def speak(self, text: str) -> None:
        if not text.strip():
            return
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, self._voice)
            # Write to temp file then play
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name

            await communicate.save(tmp_path)
            await self._play_audio(tmp_path)

            # Clean up
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass
        except ImportError:
            log.warning("edge-tts not installed, falling back to silent")
        except Exception as exc:
            log.warning("TTS playback failed: %s", exc)

    async def _play_audio(self, path: str) -> None:
        """Play an audio file using platform tools."""
        if sys.platform == "darwin":
            self._current_process = await asyncio.create_subprocess_exec(
                "afplay", path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        elif sys.platform == "win32":
            self._current_process = await asyncio.create_subprocess_exec(
                "powershell", "-c",
                f'(New-Object Media.SoundPlayer "{path}").PlaySync()',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        else:
            # Linux: try mpv, then aplay, then paplay
            for player in ("mpv --no-terminal", "aplay", "paplay"):
                cmd = player.split() + [path]
                try:
                    self._current_process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    break
                except FileNotFoundError:
                    continue
            else:
                log.warning("No audio player found on Linux")
                return

        if self._current_process:
            await self._current_process.wait()
            self._current_process = None

    def cancel(self) -> None:
        if self._current_process and self._current_process.returncode is None:
            self._current_process.terminate()
            self._current_process = None


class SystemTTS(BaseTTS):
    """Platform system TTS — instant, robotic, no internet needed."""

    def __init__(self):
        self._current_process = None

    async def speak(self, text: str) -> None:
        if not text.strip():
            return
        try:
            if sys.platform == "darwin":
                self._current_process = await asyncio.create_subprocess_exec(
                    "say", text,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            elif sys.platform == "win32":
                ps_cmd = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$s.Speak('{text.replace(chr(39), chr(39)+chr(39))}');"
                )
                self._current_process = await asyncio.create_subprocess_exec(
                    "powershell", "-c", ps_cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            else:
                self._current_process = await asyncio.create_subprocess_exec(
                    "espeak", text,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )

            if self._current_process:
                await self._current_process.wait()
                self._current_process = None
        except FileNotFoundError:
            log.warning("System TTS not available on this platform")
        except Exception as exc:
            log.warning("System TTS failed: %s", exc)

    def cancel(self) -> None:
        if self._current_process and self._current_process.returncode is None:
            self._current_process.terminate()
            self._current_process = None


class NoopTTS(BaseTTS):
    """Silent — voice input only, no playback."""
    pass


def create_tts(engine: str) -> BaseTTS:
    """Factory function for TTS engines."""
    if engine == "edge":
        return EdgeTTS()
    elif engine == "system":
        return SystemTTS()
    return NoopTTS()
