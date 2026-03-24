"""Speech-to-text via local Whisper (faster-whisper).

Transcription runs in a subprocess to avoid multiprocessing conflicts
with Textual's event loop file descriptors.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


class WhisperSTT:
    """Local Whisper transcription via faster-whisper.

    All inference runs in a clean subprocess to isolate from Textual's
    event loop. The model is downloaded on first use (~140MB for base).
    """

    def __init__(self, model_name: str = "base", language: str = "en"):
        self._model_name = model_name
        self._language = language

    async def transcribe(self, audio, sample_rate: int = 16000) -> str:
        """Transcribe audio buffer to text via subprocess."""
        import numpy as np

        if not isinstance(audio, np.ndarray) or audio.size == 0:
            return ""

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
            script = (
                "import sys, json\n"
                "from faster_whisper import WhisperModel\n"
                f"m = WhisperModel('{self._model_name}', device='cpu', compute_type='int8', num_workers=1)\n"
                f"segs, info = m.transcribe('{tmp_path}', language='{self._language}', beam_size=5, vad_filter=True)\n"
                "text = ' '.join(s.text.strip() for s in segs)\n"
                "print(text)\n"
            )
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                text = stdout.decode().strip()
                log.info("Transcribed: '%s'", text[:80])
                return text
            else:
                err = stderr.decode().strip()
                log.error("Transcription subprocess failed: %s", err[:200])
                return ""
        except Exception as exc:
            log.error("Transcription failed: %s", exc)
            return ""
        finally:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass
