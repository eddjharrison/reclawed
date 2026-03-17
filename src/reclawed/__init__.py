"""Re:Clawed — WhatsApp-style TUI for Claude CLI."""

__version__ = "0.1.0"

# Prevent subprocess console windows on Windows — must run before any
# other module imports subprocess (including the Claude Agent SDK).
import sys as _sys
if _sys.platform == "win32":
    import subprocess as _sp
    import os as _os
    _orig_popen_init = _sp.Popen.__init__
    _CREATE_NO_WINDOW = 0x08000000

    def _no_window_popen_init(self, *args, **kwargs):  # type: ignore
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_NO_WINDOW
        # Log subprocess spawns for debugging
        _log = _os.path.join(_os.environ.get("LOCALAPPDATA", "."), "reclawed", "subprocess.log")
        try:
            import traceback as _tb
            _cmd = str(args[0] if args else kwargs.get("args", "?"))[:200]
            _flags = kwargs.get("creationflags", 0)
            with open(_log, "a") as _f:
                _f.write(f"CMD: {_cmd}\nFLAGS: {_flags}\nSTACK: {''.join(_tb.format_stack()[-4:-1])}\n---\n")
        except Exception:
            pass
        _orig_popen_init(self, *args, **kwargs)

    _sp.Popen.__init__ = _no_window_popen_init  # type: ignore
