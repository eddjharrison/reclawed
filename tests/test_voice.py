"""Tests for voice mode — config, engine, STT, TTS."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawdia.config import Config


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_voice_config_defaults():
    cfg = Config()
    assert cfg.voice_enabled is False
    assert cfg.voice_stt_engine == "whisper"
    assert cfg.voice_tts_engine == "edge"
    assert cfg.voice_whisper_model == "base"
    assert cfg.voice_auto_send is True
    assert cfg.voice_auto_play is True
    assert cfg.voice_language == "en"


def test_voice_config_roundtrip(tmp_path):
    cfg = Config(
        voice_enabled=True,
        voice_tts_engine="system",
        voice_whisper_model="small",
        voice_auto_send=False,
        voice_auto_play=False,
        voice_language="fr",
    )
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    assert loaded.voice_enabled is True
    assert loaded.voice_tts_engine == "system"
    assert loaded.voice_whisper_model == "small"
    assert loaded.voice_auto_send is False
    assert loaded.voice_auto_play is False
    assert loaded.voice_language == "fr"


def test_voice_config_not_written_when_default(tmp_path):
    cfg = Config()  # all defaults
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    content = config_file.read_text()
    assert "voice_enabled" not in content
    assert "voice_tts_engine" not in content
    assert "voice_whisper_model" not in content


# ---------------------------------------------------------------------------
# is_voice_available
# ---------------------------------------------------------------------------


def test_voice_available_with_deps():
    with patch.dict("sys.modules", {"sounddevice": MagicMock(), "numpy": MagicMock()}):
        from clawdia.voice import is_voice_available
        # Re-evaluate since modules are mocked
        assert is_voice_available() is True


def test_voice_available_without_deps():
    from clawdia.voice import is_voice_available
    # This depends on whether sounddevice is installed in the test env
    # Just verify it returns a bool without crashing
    result = is_voice_available()
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# TTS factory
# ---------------------------------------------------------------------------


def test_tts_factory_edge():
    from clawdia.voice.tts import create_tts, EdgeTTS
    tts = create_tts("edge")
    assert isinstance(tts, EdgeTTS)


def test_tts_factory_system():
    from clawdia.voice.tts import create_tts, SystemTTS
    tts = create_tts("system")
    assert isinstance(tts, SystemTTS)


def test_tts_factory_none():
    from clawdia.voice.tts import create_tts, NoopTTS
    tts = create_tts("none")
    assert isinstance(tts, NoopTTS)


async def test_noop_tts_silent():
    from clawdia.voice.tts import NoopTTS
    tts = NoopTTS()
    await tts.speak("hello")  # should not raise


# ---------------------------------------------------------------------------
# WhisperSTT
# ---------------------------------------------------------------------------


async def test_whisper_stt_empty_audio():
    try:
        import numpy as np
    except ImportError:
        pytest.skip("numpy not installed")
    from clawdia.voice.stt import WhisperSTT
    stt = WhisperSTT()
    result = await stt.transcribe(np.array([], dtype=np.float32))
    assert result == ""


# ---------------------------------------------------------------------------
# MicrophoneRecorder
# ---------------------------------------------------------------------------


def test_recorder_initial_state():
    try:
        from clawdia.voice.recorder import MicrophoneRecorder
    except ImportError:
        pytest.skip("voice deps not installed")
    rec = MicrophoneRecorder()
    assert rec.is_recording is False


# ---------------------------------------------------------------------------
# Sentence extraction
# ---------------------------------------------------------------------------


def test_extract_tts_sentences():
    from clawdia.screens.chat import ChatScreen
    # Complete sentences
    assert ChatScreen._extract_tts_sentences("Hello world. How are you? Fine.") == [
        "Hello world.", "How are you?"
    ]
    # Incomplete last sentence
    assert ChatScreen._extract_tts_sentences("First sentence. Second sent") == [
        "First sentence."
    ]
    # No complete sentences
    assert ChatScreen._extract_tts_sentences("Just some text") == []
    # Empty
    assert ChatScreen._extract_tts_sentences("") == []


# ---------------------------------------------------------------------------
# Relay protocol voice field
# ---------------------------------------------------------------------------


def test_relay_message_voice_field():
    from clawdia.relay.protocol import RelayMessage
    msg = RelayMessage(
        type="message", room_id="r1", sender_id="s1",
        sender_name="Ed", sender_type="human",
        timestamp="2026-01-01T00:00:00Z",
        content="Hello",
        voice=True,
    )
    assert msg.voice is True
    # Serialization includes voice=True
    import json
    data = json.loads(msg.to_json())
    assert data["voice"] is True


def test_relay_message_voice_default_false():
    from clawdia.relay.protocol import RelayMessage
    msg = RelayMessage(
        type="message", room_id="r1", sender_id="s1",
        sender_name="Ed", sender_type="human",
        timestamp="2026-01-01T00:00:00Z",
        content="Hello",
    )
    assert msg.voice is False
    # voice=False should NOT be in serialized output (optimization)
    import json
    data = json.loads(msg.to_json())
    assert "voice" not in data


def test_relay_message_voice_roundtrip():
    from clawdia.relay.protocol import RelayMessage
    msg = RelayMessage(
        type="message", room_id="r1", sender_id="s1",
        sender_name="Ed", sender_type="human",
        timestamp="2026-01-01T00:00:00Z",
        content="Hello",
        voice=True,
    )
    restored = RelayMessage.from_json(msg.to_json())
    assert restored.voice is True
    assert restored.content == "Hello"
