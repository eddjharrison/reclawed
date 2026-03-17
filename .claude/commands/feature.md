# /feature — Implement a feature from the backlog

Pick up and implement a feature from FEATURES.md.

## Arguments

- A description or keyword matching a feature in FEATURES.md (e.g., `/feature message queue`, `/feature resizable sidebar`)
- If no argument, list the uncompleted features and ask which one to work on

## Steps

1. Read `FEATURES.md` and find the matching feature
2. Read `CLAUDE.md` for architecture rules and conventions
3. Enter plan mode and outline the implementation approach:
   - Which files need changes
   - What new files/widgets/screens are needed
   - How it integrates with existing architecture
   - Edge cases and platform considerations
4. Get user confirmation on the plan
5. Implement incrementally — small working steps, tests alongside
6. Run `python -m pytest tests/ -v -k "not relay and not daemon"` after each change
7. Mark the feature as `[x]` in FEATURES.md when complete
