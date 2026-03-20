"""Modal launcher for code review — pick working tree, branch compare, or PR."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.suggester import SuggestFromList
from textual.widgets import Button, Input, Label, RadioButton, RadioSet


class ReviewLauncherScreen(ModalScreen[dict | None]):
    """Let the user choose a review mode and parameters."""

    DEFAULT_CSS = """
    ReviewLauncherScreen {
        align: center middle;
    }
    ReviewLauncherScreen > #launcher-outer {
        width: 60;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        layout: vertical;
    }
    #launcher-outer > Label.section-title {
        width: 100%;
        text-style: bold;
        margin: 1 0 0 0;
    }
    #launcher-outer > .mode-body {
        width: 100%;
        height: auto;
        padding: 0 2;
        display: none;
    }
    #launcher-outer > .mode-body.visible {
        display: block;
    }
    #launcher-outer Input {
        width: 100%;
        margin: 0 0 1 0;
    }
    #launcher-outer Button {
        width: 100%;
        margin: 1 0 0 0;
    }
    #launcher-outer RadioSet {
        width: 100%;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def __init__(self, cwd: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cwd = cwd or "."
        self._branch_suggester = SuggestFromList([], case_sensitive=False)

    def compose(self) -> ComposeResult:
        with Vertical(id="launcher-outer"):
            yield Label("\u2318 CODE REVIEW", id="launcher-title")

            yield Label("Mode")
            yield RadioSet(
                RadioButton("Working Tree", value=True, id="mode-wt"),
                RadioButton("Branch Compare", id="mode-branch"),
                RadioButton("Pull Request", id="mode-pr"),
                id="mode-picker",
            )

            # Working Tree options
            with Vertical(id="body-wt", classes="mode-body visible"):
                yield RadioSet(
                    RadioButton("Staged", value=True, id="wt-staged"),
                    RadioButton("Unstaged", id="wt-unstaged"),
                    RadioButton("All", id="wt-all"),
                    id="wt-options",
                )
                yield Button("Review", variant="primary", id="btn-wt")

            # Branch Compare options
            with Vertical(id="body-branch", classes="mode-body"):
                yield Input(
                    placeholder="Base branch (e.g. main)",
                    id="branch-base",
                    suggester=self._branch_suggester,
                )
                yield Input(
                    placeholder="Head (default: HEAD)",
                    id="branch-head",
                    value="HEAD",
                    suggester=self._branch_suggester,
                )
                yield Button("Review", variant="primary", id="btn-branch")

            # PR options
            with Vertical(id="body-pr", classes="mode-body"):
                yield Input(placeholder="PR number", id="pr-number")
                yield Button("Review", variant="primary", id="btn-pr")

    async def on_mount(self) -> None:
        """Fetch git branches for autocomplete."""
        try:
            from reclawed.git_utils import git_branches
            branches = await git_branches(self._cwd)
            # Also include common refs
            branches = list(dict.fromkeys(branches + ["HEAD", "main", "master"]))
            self._branch_suggester._suggestions = branches
            self._branch_suggester._for_comparison = [
                b.casefold() for b in branches
            ]
            self._branch_suggester.cache.clear()
        except Exception:
            pass  # fail silently — autocomplete just won't work

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id != "mode-picker":
            return
        # Map pressed index to body ID
        bodies = ["body-wt", "body-branch", "body-pr"]
        for bid in bodies:
            body = self.query_one(f"#{bid}")
            body.remove_class("visible")
        if 0 <= event.index < len(bodies):
            self.query_one(f"#{bodies[event.index]}").add_class("visible")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-wt":
            wt_set = self.query_one("#wt-options", RadioSet)
            idx = wt_set.pressed_index
            if idx == 0:
                self.dismiss({"mode": "working_tree", "staged": True})
            elif idx == 1:
                self.dismiss({"mode": "working_tree", "staged": False})
            else:
                # "All" — staged=None signals both
                self.dismiss({"mode": "working_tree", "staged": None})
        elif btn_id == "btn-branch":
            base = self.query_one("#branch-base", Input).value.strip()
            head = self.query_one("#branch-head", Input).value.strip() or "HEAD"
            if not base:
                self.notify("Base branch is required", severity="warning", timeout=3)
                return
            self.dismiss({"mode": "branch", "base": base, "head": head})
        elif btn_id == "btn-pr":
            pr_str = self.query_one("#pr-number", Input).value.strip()
            if not pr_str.isdigit():
                self.notify("Enter a valid PR number", severity="warning", timeout=3)
                return
            self.dismiss({"mode": "pr", "number": int(pr_str)})

    def action_cancel(self) -> None:
        self.dismiss(None)
