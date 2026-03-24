"""Voice mode for Clawdia — speech-to-text input and text-to-speech output.

Optional dependency: install with ``pip install clawdia[voice]``.
"""

from __future__ import annotations


def is_voice_available() -> bool:
    """Check if voice dependencies are installed."""
    try:
        import sounddevice  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


# Lazy imports to avoid ImportError when voice deps aren't installed
def VoiceEngine(*args, **kwargs):  # noqa: N802
    """Factory — import and construct the real VoiceEngine."""
    from clawdia.voice.engine import VoiceEngine as _VoiceEngine
    return _VoiceEngine(*args, **kwargs)
