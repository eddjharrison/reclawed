"""Dedicated hooks management screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select

from reclawed.claude_settings import (
    ClaudeSettingsManager,
    HookEntry,
    HookGroup,
    ScopedHook,
    HOOK_EVENTS,
)


class HooksManagerScreen(ModalScreen[bool]):
    """Full-screen hooks management modal.

    Dismisses with True if any hooks were added, edited, moved, or removed.
    """

    DEFAULT_CSS = """
    HooksManagerScreen {
        align: center middle;
    }
    HooksManagerScreen > #hooks-dialog {
        width: 90;
        height: auto;
        max-height: 40;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    HooksManagerScreen #hooks-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    HooksManagerScreen #hooks-scroll {
        width: 100%;
        height: auto;
        max-height: 30;
    }
    HooksManagerScreen .hook-item {
        width: 100%;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
        border-bottom: solid $primary 20%;
    }
    HooksManagerScreen .hook-header {
        width: 100%;
        height: 3;
    }
    HooksManagerScreen .hook-event-name {
        width: 20;
        text-style: bold;
        padding: 1 0 0 0;
    }
    HooksManagerScreen .hook-scope-select {
        width: 14;
    }
    HooksManagerScreen .hook-cmd {
        width: 100%;
        height: 1;
        color: $text-muted;
    }
    HooksManagerScreen .hook-meta {
        width: 100%;
        height: 1;
        color: $text-disabled;
    }
    HooksManagerScreen #hooks-button-bar {
        width: 100%;
        height: 3;
        margin-top: 1;
    }
    HooksManagerScreen #hooks-button-bar Button {
        margin-right: 1;
    }
    HooksManagerScreen .hook-actions Button {
        min-width: 6;
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
    ]

    def __init__(self, project_dir: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._project_dir = project_dir
        self._changed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="hooks-dialog"):
            yield Label("Hooks Manager", id="hooks-title")
            yield VerticalScroll(id="hooks-scroll")
            with Horizontal(id="hooks-button-bar"):
                yield Button("Add Hook", id="btn-add-hook", variant="primary")
                yield Button("Close", id="btn-close-hooks")

    def on_mount(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        try:
            scroll = self.query_one("#hooks-scroll", VerticalScroll)
        except Exception:
            return
        scroll.remove_children()

        mgr = ClaudeSettingsManager(project_dir=self._project_dir)
        hooks = mgr.load_hooks()

        if not hooks:
            scroll.mount(Label("No hooks configured. Click Add Hook to create one."))
            return

        scopes = [("project", "project"), ("user", "user"), ("local", "local")]

        for i, sh in enumerate(hooks):
            item = Vertical(classes="hook-item")
            scroll.mount(item)

            # Header row: event name + scope select + action buttons
            header = Horizontal(classes="hook-header")
            item.mount(header)
            header.mount(Label(sh.event, classes="hook-event-name"))
            header.mount(Select(
                scopes,
                value=sh.scope,
                id=f"sel-scope-{i}",
                classes="hook-scope-select",
                allow_blank=False,
            ))
            actions = Horizontal(classes="hook-actions")
            header.mount(actions)
            actions.mount(Button("Edit", id=f"btn-edit-hook-{i}"))
            actions.mount(Button("Del", id=f"btn-del-hook-{i}", variant="default"))

            # Command preview line
            cmd_text = "; ".join(h.command for h in sh.group.hooks)
            if len(cmd_text) > 70:
                cmd_text = cmd_text[:67] + "..."
            item.mount(Label(cmd_text, classes="hook-cmd"))

            # Meta line: timeout + matcher
            meta_parts = []
            if sh.group.hooks and sh.group.hooks[0].timeout:
                meta_parts.append(f"timeout: {sh.group.hooks[0].timeout}ms")
            if sh.group.matcher:
                meta_parts.append(f"matcher: {sh.group.matcher}")
            if meta_parts:
                item.mount(Label("  ".join(meta_parts), classes="hook-meta"))

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle scope dropdown change — move hook to new scope."""
        if not event.select.id or not event.select.id.startswith("sel-scope-"):
            return
        idx = int(event.select.id.split("-")[-1])
        new_scope = str(event.value)

        mgr = ClaudeSettingsManager(project_dir=self._project_dir)
        hooks = mgr.load_hooks()
        if not (0 <= idx < len(hooks)):
            return
        sh = hooks[idx]
        if sh.scope == new_scope:
            return

        # Remove from old scope
        scope_hooks = [h for h in hooks if h.event == sh.event and h.scope == sh.scope]
        scope_index = scope_hooks.index(sh)
        mgr.remove_hook(sh.scope, sh.event, scope_index)

        # Add to new scope
        mgr.save_hook(new_scope, sh.event, sh.group)
        self._changed = True
        self._refresh_list()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-close-hooks":
            self.dismiss(self._changed)
        elif bid == "btn-add-hook":
            self._add_hook()
        elif bid and bid.startswith("btn-edit-hook-"):
            idx = int(bid.split("-")[-1])
            self._edit_hook(idx)
        elif bid and bid.startswith("btn-del-hook-"):
            idx = int(bid.split("-")[-1])
            self._delete_hook(idx)

    def _add_hook(self) -> None:
        from reclawed.screens.settings import HookEditorScreen

        def on_dismiss(result: dict | None) -> None:
            if result:
                mgr = ClaudeSettingsManager(project_dir=self._project_dir)
                group = HookGroup(
                    matcher=result["matcher"],
                    hooks=[HookEntry(
                        command=result["command"],
                        timeout=result["timeout"],
                    )],
                )
                mgr.save_hook(result["scope"], result["event"], group)
                self._changed = True
                self._refresh_list()

        self.app.push_screen(HookEditorScreen(), on_dismiss)

    def _edit_hook(self, idx: int) -> None:
        from reclawed.screens.settings import HookEditorScreen

        mgr = ClaudeSettingsManager(project_dir=self._project_dir)
        hooks = mgr.load_hooks()
        if not (0 <= idx < len(hooks)):
            return

        def on_dismiss(result: dict | None) -> None:
            if result:
                # Reload to get freshest state before mutating
                fresh = mgr.load_hooks()
                if 0 <= idx < len(fresh):
                    target = fresh[idx]
                    scope_hooks = [
                        h for h in fresh
                        if h.event == target.event and h.scope == target.scope
                    ]
                    scope_index = scope_hooks.index(target)
                    mgr.remove_hook(target.scope, target.event, scope_index)

                new_group = HookGroup(
                    matcher=result["matcher"],
                    hooks=[HookEntry(
                        command=result["command"],
                        timeout=result["timeout"],
                    )],
                )
                mgr.save_hook(result["scope"], result["event"], new_group)
                self._changed = True
                self._refresh_list()

        self.app.push_screen(HookEditorScreen(), on_dismiss)

    def _delete_hook(self, idx: int) -> None:
        from reclawed.widgets.confirm_screen import ConfirmScreen

        mgr = ClaudeSettingsManager(project_dir=self._project_dir)
        hooks = mgr.load_hooks()
        if not (0 <= idx < len(hooks)):
            return
        sh = hooks[idx]
        cmd_preview = sh.group.hooks[0].command[:40] if sh.group.hooks else "?"

        def on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            fresh = mgr.load_hooks()
            if not (0 <= idx < len(fresh)):
                return
            target = fresh[idx]
            scope_hooks = [
                h for h in fresh
                if h.event == target.event and h.scope == target.scope
            ]
            scope_index = scope_hooks.index(target)
            mgr.remove_hook(target.scope, target.event, scope_index)
            self._changed = True
            self._refresh_list()

        self.app.push_screen(
            ConfirmScreen(title=f"Remove {sh.event} hook?", message=cmd_preview),
            on_confirm,
        )

    def action_close(self) -> None:
        self.dismiss(self._changed)
