"""Voice engine — coordinates microphone capture, STT, and TTS."""

from __future__ import annotations

import asyncio
import logging

from clawdia.config import Config
from clawdia.voice.recorder import MicrophoneRecorder
from clawdia.voice.stt import WhisperSTT
from clawdia.voice.tts import BaseTTS, create_tts

log = logging.getLogger(__name__)


class VoiceEngine:
    """Main coordinator for voice mode.

    Manages microphone recording, speech-to-text transcription,
    and text-to-speech playback.
    """

    def __init__(self, config: Config):
        self._config = config
        self._recorder = MicrophoneRecorder()
        self._stt = WhisperSTT(
            model_name=config.voice_whisper_model,
            language=config.voice_language,
        )
        self._tts: BaseTTS = create_tts(config.voice_tts_engine)
        self._tts_queue: asyncio.Queue[str] = asyncio.Queue()
        self._tts_task: asyncio.Task | None = None
        self._speaking = False

    @property
    def is_recording(self) -> bool:
        return self._recorder.is_recording

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    async def start_recording(self) -> None:
        """Start capturing from microphone."""
        # Cancel any in-progress TTS to avoid feedback
        self.cancel_playback()
        await self._recorder.start()

    async def stop_recording(self) -> str:
        """Stop capture, run STT, return transcribed text."""
        audio = await self._recorder.stop()
        if audio.size == 0:
            return ""
        text = await self._stt.transcribe(audio)
        return text

    async def speak(self, text: str) -> None:
        """Speak text via TTS. Blocks until playback completes."""
        if not text.strip():
            return
        self._speaking = True
        try:
            await self._tts.speak(text)
        finally:
            self._speaking = False

    async def speak_streaming(self, sentence: str) -> None:
        """Queue a sentence for background TTS playback.

        Sentences are played sequentially in order.
        """
        await self._tts_queue.put(sentence)
        if self._tts_task is None or self._tts_task.done():
            self._tts_task = asyncio.create_task(self._tts_worker())

    async def _tts_worker(self) -> None:
        """Background worker that plays queued sentences sequentially."""
        while not self._tts_queue.empty():
            sentence = await self._tts_queue.get()
            await self.speak(sentence)

    def cancel_playback(self) -> None:
        """Stop any in-progress TTS playback and clear the queue."""
        self._tts.cancel()
        self._speaking = False
        # Clear the queue
        while not self._tts_queue.empty():
            try:
                self._tts_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        if self._tts_task and not self._tts_task.done():
            self._tts_task.cancel()
            self._tts_task = None
