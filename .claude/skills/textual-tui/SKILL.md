---
name: textual-tui
description: >
  Textual TUI framework specialist for Re:Clawed. Covers widget composition,
  CSS styling, Rich markup, message bubbling, screen management, and
  platform-specific rendering (Windows Terminal quirks).
license: MIT
compatibility: Designed for Claude Code
allowed-tools: Read Grep Glob Bash
user-invocable: false
metadata:
  version: "1.0.0"
  category: "framework"
  status: "active"
  updated: "2026-03-17"
  tags: "textual, tui, widgets, css, rich-markup, windows"

triggers:
  keywords: ["Textual", "TUI", "widget", "screen", "TCSS", "Rich markup", "compose", "mount", "dock", "ComposeResult"]
  languages: ["python"]
---

# Textual TUI Specialist — Re:Clawed

Expert knowledge for building the Re:Clawed WhatsApp-style TUI with Textual.

## Quick Reference

**Architecture**: Textual app → Screens → Widgets → Rich markup
**Styling**: Widget-local `DEFAULT_CSS` + global `styles/app.tcss`
**State**: SQLite store + Config TOML + in-memory session state
**Platform**: Must work on Windows, macOS, Linux

### Key Patterns

**Widget Composition** — widgets yield children in `compose()`, handle events via Message classes:
```python
class MyWidget(Static):
    class Clicked(Message):
        def __init__(self, item_id: str) -> None:
            super().__init__()
            self.item_id = item_id

    def compose(self) -> ComposeResult:
        yield Label("Hello")
        yield Button("Click", id="btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.post_message(self.Clicked(self.id))
```

**Message Bubbling** — child widgets post Messages, parent screens handle them:
```python
# In ChatScreen:
def on_compose_area_submitted(self, event: ComposeArea.Submitted) -> None:
    self._send_message(event.text)
```

**Rich Markup in Static/Label** — use `[bold cyan]text[/bold cyan]` syntax:
```python
label.update("[bold green]✓[/bold green] Connected")
```

### Critical Rules

1. **No dock:bottom abuse** — causes compression bugs. Use natural vertical flow.
2. **Emoji on Windows** — Working: 📁🔋🧠🤖⚡ | Broken (eat adjacent text): ⚙🔀🔒⬤
3. **CSS in DEFAULT_CSS** — widget-specific styles in the class, layout in app.tcss
4. **Message boundaries** — never reach across widget boundaries directly
5. **Async mount** — `await self.mount(widget)` in async methods, `self.mount(widget)` in sync
6. **ID uniqueness** — use index-based IDs for dynamic lists (not label-based)
7. **ModalScreen** — use `ModalScreen[ReturnType]` for dialogs, dismiss with typed value
8. **Key handling** — `on_key(event: Key)` is more reliable than BINDINGS for modal screens
9. **Windows Terminal** — Ctrl+Enter sends `ctrl+j`, Shift+Enter same as Enter

### File Map

| File | Purpose |
|------|---------|
| `src/reclawed/screens/chat.py` | Main chat screen, compose, BINDINGS, message handling |
| `src/reclawed/widgets/status_bar.py` | Rich-markup status bar with battery gauge |
| `src/reclawed/widgets/workspace_section.py` | Custom workspace headers with color |
| `src/reclawed/widgets/chat_sidebar.py` | Session list + workspace sections |
| `src/reclawed/widgets/compose_area.py` | Text input with key handling |
| `src/reclawed/widgets/confirm_screen.py` | Reusable confirmation modal |
| `src/reclawed/widgets/ask_user_question.py` | Multi-question form widget |
| `src/reclawed/widgets/choice_buttons.py` | Clickable choice buttons |
| `src/reclawed/widgets/workspace_picker.py` | F6 workspace picker modal |
| `src/reclawed/config.py` | Config dataclass with TOML load/save |
| `src/reclawed/store.py` | SQLite persistence with migrations |
| `src/reclawed/styles/app.tcss` | Global TCSS layout |

### Common Pitfalls

- **`dock: bottom` on multiple widgets** → they stack and compress to zero height
- **Emoji width calculation** → some emoji are counted as 1 char but render as 2, eating adjacent text
- **`Collapsible` widget** → limited customization; Re:Clawed uses custom `WorkspaceSection` instead
- **`self.query_one()` failures** → wrap in try/except when widget may not exist yet
- **Rich tags in widget IDs** → `[r]` interpreted as Rich reset tag, not literal text
