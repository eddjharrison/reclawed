"""Allow running as `python -m reclawed`."""

# Apply Windows subprocess patch before any other imports
import sys
if sys.platform == "win32":
    import subprocess as _sp
    _orig_init = _sp.Popen.__init__
    _NO_WIN = _sp.CREATE_NO_WINDOW

    def _patched_init(self, *args, **kwargs):  # type: ignore
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | _NO_WIN
        _orig_init(self, *args, **kwargs)

    _sp.Popen.__init__ = _patched_init  # type: ignore

from reclawed.cli import main

main()
