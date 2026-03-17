# /dev — Launch Re:Clawed for testing

Start the Re:Clawed TUI in development mode.

## Steps

1. Ensure the virtual environment is activated
2. Check if `reclawed` command is available (`which reclawed` or `where reclawed`)
3. If not installed, run `pip install -e .` in the repo root
4. Launch with `reclawed` and inform the user it's running
5. If there are import errors or crashes, read the traceback and diagnose

## Notes

- On Windows, the TUI launches in the current terminal
- The relay daemon starts automatically if `relay_mode = "local"` in config
- Config file is at `%APPDATA%\reclawed\config.toml` (Windows) or `~/.config/reclawed/config.toml` (Linux/macOS)
