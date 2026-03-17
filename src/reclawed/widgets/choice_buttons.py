"""Clickable choice buttons rendered when Claude presents numbered options."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message as TMessage
from textual.widgets import Button


class ChoiceButtons(Horizontal):
    """Row of compact buttons for selecting from Claude's numbered choices.

    Posts ``ChoiceButtons.Selected(label, description)`` when clicked.
    """

    DEFAULT_CSS = """
    ChoiceButtons {
        width: 100%;
        height: auto;
        margin-top: 1;
    }
    ChoiceButtons Button {
        margin-right: 1;
        min-width: 6;
        height: 3;
    }
    """

    class Selected(TMessage):
        """Posted when a choice button is clicked."""

        def __init__(self, label: str, description: str) -> None:
            super().__init__()
            self.label = label
            self.description = description

    def __init__(self, choices: list[tuple[str, str]], **kwargs) -> None:
        super().__init__(**kwargs)
        self._choices = choices

    def compose(self) -> ComposeResult:
        for idx, (label, description) in enumerate(self._choices):
            # Use the label directly if it's descriptive, otherwise prefix "Option"
            btn_text = label if len(label) > 3 else f"Option {label}"
            yield Button(btn_text, id=f"choice-{idx}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        btn_id = event.button.id or ""
        idx_str = btn_id.replace("choice-", "")
        try:
            idx = int(idx_str)
            if 0 <= idx < len(self._choices):
                label, description = self._choices[idx]
                self.post_message(self.Selected(label, description))
        except ValueError:
            pass
