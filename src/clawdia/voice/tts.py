"""Text-to-speech engines — edge-tts (free), system TTS, or silent."""

from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# Best-sounding edge-tts voices per language (tested for naturalness)
RECOMMENDED_VOICES = {
    "en": "en-US-AndrewMultilingualNeural",  # very natural, good pacing
    "en-gb": "en-GB-RyanNeural",
    "fr": "fr-FR-HenriNeural",
    "de": "de-DE-ConradNeural",
    "es": "es-ES-AlvaroNeural",
    "it": "it-IT-DiegoNeural",
    "ja": "ja-JP-KeitaNeural",
    "zh": "zh-CN-YunxiNeural",
}


class BaseTTS:
    """Base class for TTS engines."""

    async def speak(self, text: str) -> None:
        """Speak the given text. Override in subclasses."""

    def cancel(self) -> None:
        """Cancel any in-progress playback. Override in subclasses."""


class EdgeTTS(BaseTTS):
    """Free Microsoft TTS via edge-tts library.

    Good quality, requires internet, no API key.
    Uses streaming audio playback for lower latency.
    """

    def __init__(self, voice: str | None = None, language: str = "en"):
        # Pick best voice for language if not specified
        self._voice = voice or RECOMMENDED_VOICES.get(language, RECOMMENDED_VOICES["en"])
        self._current_process = None
        self._cancelled = False

    async def speak(self, text: str) -> None:
        if not text.strip() or self._cancelled:
            return
        self._cancelled = False
        try:
            import edge_tts

            # Use SSML-like rate adjustment for more natural pacing
            # Slightly faster than default sounds more conversational
            communicate = edge_tts.Communicate(
                text, self._voice,
                rate="+10%",    # slightly faster — more natural for code discussion
                pitch="+0Hz",   # keep default pitch
            )

            # Stream to temp file — edge-tts doesn't support raw PCM streaming
            # but we start playback as soon as the file is written
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name

            await communicate.save(tmp_path)

            if not self._cancelled:
                await self._play_audio(tmp_path)

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
            # afplay with rate adjustment for snappier playback
            self._current_process = await asyncio.create_subprocess_exec(
                "afplay", "-r", "1.15", path,  # 15% faster playback
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
            for player in ("mpv --no-terminal --speed=1.15", "aplay", "paplay"):
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
        self._cancelled = True
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
                # Use Samantha voice on macOS — more natural than default
                self._current_process = await asyncio.create_subprocess_exec(
                    "say", "-v", "Samantha", "-r", "210", text,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            elif sys.platform == "win32":
                ps_cmd = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    "$s.Rate = 2; "
                    f"$s.Speak('{text.replace(chr(39), chr(39)+chr(39))}');"
                )
                self._current_process = await asyncio.create_subprocess_exec(
                    "powershell", "-c", ps_cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            else:
                self._current_process = await asyncio.create_subprocess_exec(
                    "espeak", "-s", "180", text,
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


def create_tts(engine: str, language: str = "en") -> BaseTTS:
    """Factory function for TTS engines."""
    if engine == "edge":
        return EdgeTTS(language=language)
    elif engine == "system":
        return SystemTTS()
    return NoopTTS()
