"""Re:Clawed — WhatsApp-style TUI for Claude CLI."""

__version__ = "0.1.0"

# Prevent subprocess console windows on Windows — must run before any
# other module imports subprocess (including the Claude Agent SDK).
import sys as _sys
if _sys.platform == "win32":
    import subprocess as _sp
    _orig_popen_init = _sp.Popen.__init__
    _CREATE_NO_WINDOW = 0x08000000  # subprocess.CREATE_NO_WINDOW

    def _no_window_popen_init(self, *args, **kwargs):  # type: ignore
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_NO_WINDOW
        _orig_popen_init(self, *args, **kwargs)

    _sp.Popen.__init__ = _no_window_popen_init  # type: ignore
