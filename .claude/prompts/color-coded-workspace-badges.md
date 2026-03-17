# Color-Coded Workspace Badges

## Goal
Each workspace gets a unique color in the status bar and sidebar, making it instantly recognizable.

## Implementation Plan

### 1. Config: Add color field to Workspace
In `src/reclawed/config.py`:
- Add `color: str = ""` to Workspace dataclass
- Auto-assign colors from a preset palette when empty
- Palette: cyan, yellow, green, magenta, blue, red (cycle for >6 workspaces)
- Load/save the color in TOML

### 2. Status Bar: Use workspace color
In `src/reclawed/widgets/status_bar.py`:
- Pass workspace color through update_info()
- Use it in Rich markup: `[bold {color}]{name}[/bold {color}]` instead of hardcoded yellow

### 3. Sidebar: Color workspace headers
In `src/reclawed/widgets/workspace_section.py`:
- Accept color parameter
- Apply to workspace name label via Rich markup or CSS class

### 4. Settings: Color picker
In `src/reclawed/screens/settings.py`:
- Allow selecting workspace color from preset palette

## Files to Modify
- src/reclawed/config.py
- src/reclawed/widgets/status_bar.py
- src/reclawed/widgets/workspace_section.py
- src/reclawed/widgets/chat_sidebar.py
- tests/test_config.py
