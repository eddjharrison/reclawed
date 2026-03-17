# /lint — Check code quality

Run linting and type checking on the Re:Clawed codebase.

## Steps

1. Run `python -m py_compile` on all `.py` files under `src/reclawed/` to catch syntax errors
2. Check for common issues:
   - Unused imports (scan for imports not referenced in the file)
   - Missing `__init__.py` files in packages
   - Files with `print()` statements (should use logging or Rich console)
3. Run `python -m pytest tests/ --co -q` (collect-only) to verify all tests are discoverable
4. Report findings grouped by severity: errors, warnings, info

## Arguments

- No args → full lint of `src/reclawed/`
- A file path → lint only that file
- `--fix` → auto-fix issues where possible (remove unused imports, etc.)
