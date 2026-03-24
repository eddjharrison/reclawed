"""Microphone capture via sounddevice."""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


class MicrophoneRecorder:
    """Captures audio from the default input device."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self._sample_rate = sample_rate
        self._channels = channels
        self._stream = None
        self._buffer: list = []
        self._recording = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    async def start(self) -> None:
        """Start capturing from microphone."""
        self._buffer.clear()
        self._recording = True
        await asyncio.to_thread(self._open_stream)

    async def stop(self):
        """Stop recording and return concatenated audio as float32 array."""
        import numpy as np
        self._recording = False
        await asyncio.to_thread(self._close_stream)
        if not self._buffer:
            return np.array([], dtype=np.float32)
        audio = np.concatenate(self._buffer)
        self._buffer.clear()
        return audio

    def _open_stream(self) -> None:
        import sounddevice as sd
        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="float32",
            callback=self._audio_callback,
        )
        self._stream.start()
        log.info("Microphone recording started (rate=%d)", self._sample_rate)

    def _close_stream(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        log.info("Microphone recording stopped (%d chunks)", len(self._buffer))

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            log.warning("Audio callback status: %s", status)
        if self._recording:
            self._buffer.append(indata[:, 0].copy())  # mono channel
