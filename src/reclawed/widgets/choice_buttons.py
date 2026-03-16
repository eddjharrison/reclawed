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
        min-width: 8;
        height: 1;
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
        for label, description in self._choices:
            short = description[:30] + "..." if len(description) > 30 else description
            yield Button(f"{label}. {short}", id=f"choice-{label}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        btn_id = event.button.id or ""
        label = btn_id.replace("choice-", "")
        for choice_label, description in self._choices:
            if choice_label == label:
                self.post_message(self.Selected(label, description))
                break
