# /test — Run the test suite

Run the Re:Clawed test suite and report results.

## Steps

1. Activate the virtual environment if not already active
2. Run `python -m pytest tests/ -v -k "not relay and not daemon"` for the fast suite
3. If the user passed `--all` or `--full`, run `python -m pytest tests/ -v` instead (includes relay + daemon tests)
4. Report: total passed, failed, skipped, and any error details
5. If tests fail, read the failing test file and the source file it tests, diagnose the root cause, and suggest a fix

## Arguments

- No args → fast suite (excludes relay/daemon)
- `--all` or `--full` → full suite including relay and daemon integration tests
- `--slow` → only slow-marked tests (`-m slow`)
- Any other args → passed directly to pytest (e.g., `/test tests/test_store.py -v`)
