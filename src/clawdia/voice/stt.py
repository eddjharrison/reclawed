"""Speech-to-text via local Whisper (faster-whisper)."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)


class WhisperSTT:
    """Local Whisper transcription via faster-whisper.

    The model is lazy-loaded on first transcription to avoid startup cost.
    Model loading and inference run in a subprocess to avoid multiprocessing
    conflicts with Textual's event loop file descriptors.
    """

    def __init__(self, model_name: str = "base", language: str = "en"):
        self._model = None
        self._model_name = model_name
        self._language = language
        self._model_load_attempted = False

    def _ensure_model(self):
        if self._model is None and not self._model_load_attempted:
            self._model_load_attempted = True
            try:
                # Suppress multiprocessing resource tracker issues
                os.environ["TOKENIZERS_PARALLELISM"] = "false"
                log.info("Loading Whisper model '%s'...", self._model_name)
                from faster_whisper import WhisperModel
                self._model = WhisperModel(
                    self._model_name,
                    device="cpu",  # force CPU to avoid multiprocessing GPU init
                    compute_type="int8",
                    num_workers=1,
                )
                log.info("Whisper model loaded")
            except Exception as exc:
                log.error("Failed to load Whisper model: %s", exc)
                self._model = None

    async def transcribe(self, audio, sample_rate: int = 16000) -> str:
        """Transcribe audio buffer to text."""
        import numpy as np

        if not isinstance(audio, np.ndarray) or audio.size == 0:
            return ""

        # Try in-process first; fall back to subprocess if multiprocessing conflicts
        try:
            return await asyncio.to_thread(self._transcribe_sync, audio, sample_rate)
        except (ValueError, OSError) as exc:
            if "fds_to_keep" in str(exc) or "bad value" in str(exc):
                log.warning("In-process transcription failed (FD conflict), using subprocess")
                return await self._transcribe_subprocess(audio, sample_rate)
            raise

    def _transcribe_sync(self, audio, sample_rate: int) -> str:
        self._ensure_model()
        if self._model is None:
            return "(Whisper model not available)"
        segments, info = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments)
        log.info("Transcribed: '%s' (lang=%s, prob=%.2f)", text[:80], info.language, info.language_probability)
        return text.strip()

    async def _transcribe_subprocess(self, audio, sample_rate: int) -> str:
        """Fallback: write audio to temp file, transcribe in a clean subprocess."""
        import numpy as np

        # Write audio to temp WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            import wave
            with wave.open(f, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes((audio * 32767).astype(np.int16).tobytes())

        try:
            # Run transcription in a clean subprocess
            script = (
                f"import sys; "
                f"from faster_whisper import WhisperModel; "
                f"m = WhisperModel('{self._model_name}', device='cpu', compute_type='int8', num_workers=1); "
                f"segs, _ = m.transcribe('{tmp_path}', language='{self._language}', beam_size=5, vad_filter=True); "
                f"print(' '.join(s.text.strip() for s in segs))"
            )
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                text = stdout.decode().strip()
                log.info("Subprocess transcribed: '%s'", text[:80])
                return text
            else:
                log.error("Subprocess transcription failed: %s", stderr.decode()[:200])
                return "(Transcription failed)"
        finally:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass
