"""Voice engine — coordinates microphone capture, STT, and TTS."""

from __future__ import annotations

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
        self._tts: BaseTTS = create_tts(config.voice_tts_engine, language=config.voice_language)
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
        """Send a sentence for pipelined TTS playback.

        Delegates to the TTS engine's streaming method which pipelines
        generation and playback — while one sentence plays, the next
        is being generated.
        """
        if not sentence.strip():
            return
        self._speaking = True
        await self._tts.speak_streaming(sentence)

    async def finish_streaming(self) -> None:
        """Signal end of streaming and wait for remaining playback."""
        try:
            await self._tts.stop_stream()
        finally:
            self._speaking = False

    def cancel_playback(self) -> None:
        """Stop any in-progress TTS playback."""
        self._tts.cancel()
        self._speaking = False
