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


# Subprocess script for pipelined streaming TTS.
# Three concurrent tasks: reader → generator → player.
# While sentence N plays, sentence N+1 is being generated.
_STREAM_SCRIPT = r'''
import asyncio, sys, os, tempfile, edge_tts

VOICE = sys.argv[1]
RATE = sys.argv[2]
PLAYER = sys.argv[3]

async def main():
    gen_queue = asyncio.Queue()
    play_queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    async def reader():
        """Read sentences from stdin, one per line."""
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                await gen_queue.put(None)
                break
            text = line.strip()
            if text:
                await gen_queue.put(text)

    async def generator():
        """Generate mp3 from each sentence via edge-tts API."""
        while True:
            text = await gen_queue.get()
            if text is None:
                await play_queue.put(None)
                break
            try:
                c = edge_tts.Communicate(text, VOICE, rate=RATE)
                f = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
                f.close()
                await c.save(f.name)
                await play_queue.put(f.name)
            except Exception as e:
                print(f'TTS gen error: {e}', file=sys.stderr)

    async def player():
        """Play mp3 files sequentially."""
        while True:
            path = await play_queue.get()
            if path is None:
                break
            proc = await asyncio.create_subprocess_exec(
                *PLAYER.split(), path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            try:
                os.unlink(path)
            except OSError:
                pass

    await asyncio.gather(reader(), generator(), player())

asyncio.run(main())
'''


class BaseTTS:
    """Base class for TTS engines."""

    async def speak(self, text: str) -> None:
        """Speak the given text. Override in subclasses."""

    async def speak_streaming(self, sentence: str) -> None:
        """Queue a sentence for pipelined playback. Override in subclasses."""
        await self.speak(sentence)

    async def stop_stream(self) -> None:
        """Signal end of streaming input and wait for remaining playback."""

    def cancel(self) -> None:
        """Cancel any in-progress playback. Override in subclasses."""


class EdgeTTS(BaseTTS):
    """Free Microsoft TTS via edge-tts library.

    Good quality, requires internet, no API key.
    Runs in a subprocess to avoid event loop conflicts with Textual.

    For streaming, uses a persistent pipelined subprocess: while one sentence
    plays, the next is being generated — eliminating inter-sentence gaps.
    """

    def __init__(self, voice: str | None = None, language: str = "en", rate: str = "+8%"):
        self._voice = voice or RECOMMENDED_VOICES.get(language, RECOMMENDED_VOICES["en"])
        self._rate = rate
        self._current_process: asyncio.subprocess.Process | None = None
        self._stream_process: asyncio.subprocess.Process | None = None
        self._cancelled = False

    async def speak(self, text: str) -> None:
        """Speak a single utterance (one subprocess, generate + play)."""
        self._cancelled = False
        text = _clean_for_speech(text)
        if not text:
            return
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8",
            ) as f:
                f.write(text)
                text_path = f.name

            player = "afplay" if sys.platform == "darwin" else "mpv --no-terminal"
            script = (
                "import asyncio, os, tempfile, edge_tts\n"
                f"text = open({text_path!r}, encoding='utf-8').read()\n"
                f"os.unlink({text_path!r})\n"
                "async def main():\n"
                f"    c = edge_tts.Communicate(text, {self._voice!r}, rate={self._rate!r})\n"
                "    f = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)\n"
                "    f.close()\n"
                "    await c.save(f.name)\n"
                f"    os.system({player!r} + ' ' + f.name)\n"
                "    os.unlink(f.name)\n"
                "asyncio.run(main())\n"
            )

            self._current_process = await asyncio.create_subprocess_exec(
                sys.executable, "-c", script,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await self._current_process.communicate()

            if self._current_process.returncode != 0 and not self._cancelled:
                err = stderr.decode()[:200] if stderr else "unknown error"
                log.warning("TTS subprocess failed (rc=%d): %s", self._current_process.returncode, err)

            self._current_process = None
        except asyncio.CancelledError:
            if self._current_process:
                self._current_process.terminate()
                self._current_process = None
            try:
                Path(text_path).unlink(missing_ok=True)
            except (NameError, OSError):
                pass
            raise
        except Exception as exc:
            log.warning("TTS failed: %s", exc)

    async def speak_streaming(self, sentence: str) -> None:
        """Send a sentence to the pipelined streaming subprocess.

        Spawns the subprocess on first call. Sentences are generated and
        played with overlap — while one plays, the next is being generated.
        """
        self._cancelled = False
        sentence = _clean_for_speech(sentence)
        if not sentence:
            return

        # Ensure streaming subprocess is running
        if not self._stream_process or self._stream_process.returncode is not None:
            await self._start_stream()

        try:
            self._stream_process.stdin.write((sentence + "\n").encode("utf-8"))
            await self._stream_process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            log.warning("TTS stream write failed: %s", exc)
            self._stream_process = None

    async def _start_stream(self) -> None:
        """Launch the persistent pipelined TTS subprocess."""
        player = "afplay" if sys.platform == "darwin" else "mpv --no-terminal"
        self._stream_process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", _STREAM_SCRIPT,
            self._voice, self._rate, player,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

    async def stop_stream(self) -> None:
        """Close stdin to signal no more sentences, wait for remaining playback."""
        if not self._stream_process or self._stream_process.returncode is not None:
            self._stream_process = None
            return
        try:
            self._stream_process.stdin.close()
            await self._stream_process.stdin.wait_closed()
        except OSError:
            pass
        try:
            _, stderr = await asyncio.wait_for(
                self._stream_process.communicate(), timeout=60,
            )
            if self._stream_process.returncode != 0 and not self._cancelled:
                err = stderr.decode()[:200] if stderr else ""
                if err:
                    log.warning("TTS stream subprocess errors: %s", err)
        except asyncio.TimeoutError:
            self._stream_process.terminate()
        self._stream_process = None

    def cancel(self) -> None:
        self._cancelled = True
        if self._stream_process and self._stream_process.returncode is None:
            self._stream_process.terminate()
            self._stream_process = None
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
