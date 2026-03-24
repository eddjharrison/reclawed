"""Text-to-speech engines — edge-tts (free), system TTS, or silent."""

from __future__ import annotations

import asyncio
import logging
import re
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# Most natural-sounding edge-tts voices (tested March 2026)
RECOMMENDED_VOICES = {
    "en": "en-US-AvaMultilingualNeural",
    "en-gb": "en-GB-SoniaNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "it": "it-IT-ElsaNeural",
    "ja": "ja-JP-NanamiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
}


def _clean_for_speech(text: str) -> str:
    """Strip markdown/code artifacts that sound terrible when spoken.

    Converts technical text into something a TTS engine can read naturally.
    """
    # Remove code blocks entirely — reading code aloud is useless
    text = re.sub(r'```[\s\S]*?```', ' (code omitted) ', text)
    # Remove inline code backticks
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Remove markdown bold/italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    # Remove markdown headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove markdown links — keep the label
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove bullet points
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
    # Remove numbered list prefixes
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Remove horizontal rules
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
    # Remove table formatting
    text = re.sub(r'\|', ' ', text)
    # Collapse multiple spaces/newlines
    text = re.sub(r'\n{2,}', '. ', text)
    text = re.sub(r'\n', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    # Remove tool activity lines (Reading file.py..., Running: pytest, etc.)
    text = re.sub(r'\*\*(Reading|Editing|Writing|Running|Searching)\*\*\s+[^\n]+', '', text)
    # Clean up repeated dots and punctuation
    text = re.sub(r'\.{2,}', '.', text)
    text = re.sub(r'\.\s*\.', '.', text)
    text = re.sub(r'\(\s*\)', '', text)
    return text.strip()


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

    def __init__(self, voice: str | None = None, language: str = "en"):
        self._voice = voice or RECOMMENDED_VOICES.get(language, RECOMMENDED_VOICES["en"])
        self._current_process = None
        self._cancelled = False

    async def speak(self, text: str) -> None:
        text = _clean_for_speech(text)
        if not text or self._cancelled:
            return
        self._cancelled = False
        try:
            # Fire-and-forget subprocess: generates audio + plays it.
            # Does NOT block Textual's event loop.
            player = "afplay" if sys.platform == "darwin" else "mpv --no-terminal"
            script = (
                "import asyncio, sys, os, tempfile, edge_tts\n"
                "async def main():\n"
                "    text = sys.stdin.read()\n"
                f"    c = edge_tts.Communicate(text, '{self._voice}')\n"
                "    f = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)\n"
                "    f.close()\n"
                "    await c.save(f.name)\n"
                f"    os.system('{player} ' + f.name)\n"
                "    os.unlink(f.name)\n"
                "asyncio.run(main())\n"
            )

            self._current_process = await asyncio.create_subprocess_exec(
                sys.executable, "-c", script,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            # Send text via stdin — safe for any content
            self._current_process.stdin.write(text.encode())
            self._current_process.stdin.close()
            # DON'T await proc.wait() — let it play in the background
        except Exception as exc:
            log.warning("TTS launch failed: %s", exc)

    async def _play_audio(self, path: str) -> None:
        """Play an audio file at natural speed."""
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
        self._cancelled = True
        if self._current_process and self._current_process.returncode is None:
            self._current_process.terminate()
            self._current_process = None


class SystemTTS(BaseTTS):
    """Platform system TTS — instant, no internet needed."""

    def __init__(self):
        self._current_process = None

    async def speak(self, text: str) -> None:
        text = _clean_for_speech(text)
        if not text:
            return
        try:
            if sys.platform == "darwin":
                self._current_process = await asyncio.create_subprocess_exec(
                    "say", "-v", "Samantha", text,
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


def create_tts(engine: str, language: str = "en") -> BaseTTS:
    """Factory function for TTS engines."""
    if engine == "edge":
        return EdgeTTS(language=language)
    elif engine == "system":
        return SystemTTS()
    return NoopTTS()
