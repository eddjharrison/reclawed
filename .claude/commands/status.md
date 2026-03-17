# /status — Project status overview

Show a quick status summary of the Re:Clawed project.

## Steps

1. **Git status**: current branch, uncommitted changes, ahead/behind remote
2. **Recent commits**: last 5 commits with short hash and message
3. **Open PRs**: use `gh pr list --limit 5` if gh is available
4. **Open issues**: use `gh issue list --limit 5` if gh is available
5. **Test health**: run `python -m pytest tests/ -v -k "not relay and not daemon" --tb=no -q` and report pass/fail counts
6. **Feature backlog**: count remaining unchecked items in FEATURES.md
7. **Dependencies**: check if venv exists and packages are installed

## Output Format

Present as a clean summary with sections, not raw command output. Use bullet points.
