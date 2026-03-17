# Feature Backlog

Show and manage the Re:Clawed feature backlog.

## Instructions

Read `$CLAUDE_PROJECT_DIR/FEATURES.md` and present a summary:

1. **By section** — for each `##` heading, count completed `[x]` vs remaining `[ ]`
2. **Remaining items** — list all unchecked `[ ]` items grouped by section
3. **Progress bar** — show overall completion percentage

If `$ARGUMENTS` contains "next", suggest the most impactful next feature to build based on:
- Dependencies (what unblocks other features)
- User value (what improves daily usage most)
- Complexity (quick wins vs big lifts)

Format:
```
FEATURE BACKLOG
===============
Section              Done  Left
─────────────────────────────────
Workspaces            9/10   1
Settings              3/5    2
...
─────────────────────────────────
Total:               X/Y  (Z%)

NEXT UP:
1. [feature] — [why it's high priority]
2. [feature] — [why]
3. [feature] — [why]
```
