"""Speech-to-text via local Whisper (faster-whisper)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)


class WhisperSTT:
    """Local Whisper transcription via faster-whisper.

    The model is lazy-loaded on first transcription to avoid startup cost.
    """

    def __init__(self, model_name: str = "base", language: str = "en"):
        self._model = None
        self._model_name = model_name
        self._language = language

    def _ensure_model(self):
        if self._model is None:
            log.info("Loading Whisper model '%s'...", self._model_name)
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self._model_name,
                device="auto",
                compute_type="int8",
            )
            log.info("Whisper model loaded")

    async def transcribe(self, audio, sample_rate: int = 16000) -> str:
        """Transcribe audio buffer to text. Runs model inference in a thread."""
        if audio.size == 0:
            return ""
        return await asyncio.to_thread(self._transcribe_sync, audio, sample_rate)

    def _transcribe_sync(self, audio, sample_rate: int) -> str:
        self._ensure_model()
        segments, info = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments)
        log.info("Transcribed: '%s' (lang=%s, prob=%.2f)", text[:80], info.language, info.language_probability)
        return text.strip()
