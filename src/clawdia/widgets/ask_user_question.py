"""Widget for AskUserQuestion tool — multi-question form with clickable options."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message as TMessage
from textual.widgets import Button, Label


class AskUserQuestionWidget(Vertical):
    """Renders one or more questions with clickable option buttons.

    Collects answers for all questions. When all are answered, shows
    a Submit button. Posts ``Submitted(answers)`` when submitted.
    """

    DEFAULT_CSS = """
    AskUserQuestionWidget {
        width: 100%;
        height: auto;
        margin-top: 1;
    }
    AskUserQuestionWidget .auq-question {
        width: 100%;
        margin-top: 1;
        text-style: bold;
    }
    AskUserQuestionWidget .auq-option {
        margin-right: 1;
        height: 3;
        min-width: 8;
    }
    AskUserQuestionWidget .auq-option.selected {
        background: $accent;
        color: $text;
        text-style: bold;
    }
    AskUserQuestionWidget .auq-options-row {
        width: 100%;
        height: auto;
        layout: horizontal;
    }
    AskUserQuestionWidget .auq-submit {
        margin-top: 1;
        width: auto;
        min-width: 12;
        display: none;
    }
    AskUserQuestionWidget .auq-submit.visible {
        display: block;
    }
    """

    class Submitted(TMessage):
        """Posted when the user submits all answers."""

        def __init__(self, answers: str) -> None:
            super().__init__()
            self.answers = answers

    def __init__(self, questions: list[dict], **kwargs) -> None:
        super().__init__(**kwargs)
        self._questions = questions
        # Track selected answer per question index
        self._answers: dict[int, tuple[str, str]] = {}

    def compose(self) -> ComposeResult:
        for q_idx, q in enumerate(self._questions):
            header = q.get("header", "")
            q_text = q.get("question", "")
            display = f"{header}: {q_text}" if header else q_text
            yield Label(display, classes="auq-question")

            with Vertical(classes="auq-options-row"):
                options = q.get("options", [])
                for o_idx, opt in enumerate(options):
                    label = opt.get("label", str(o_idx + 1)) if isinstance(opt, dict) else str(opt)
                    btn = Button(label, id=f"auq-{q_idx}-{o_idx}", classes="auq-option")
                    # Stash metadata
                    btn._q_idx = q_idx  # type: ignore[attr-defined]
                    btn._o_idx = o_idx  # type: ignore[attr-defined]
                    btn._label_text = label  # type: ignore[attr-defined]
                    desc = opt.get("description", "") if isinstance(opt, dict) else ""
                    btn._desc = desc  # type: ignore[attr-defined]
                    yield btn

        yield Button("Submit answers", id="auq-submit", classes="auq-submit", variant="success")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        btn = event.button

        if btn.id == "auq-submit":
            self._do_submit()
            return

        q_idx = getattr(btn, "_q_idx", None)
        o_idx = getattr(btn, "_o_idx", None)
        label_text = getattr(btn, "_label_text", "")
        desc = getattr(btn, "_desc", "")

        if q_idx is None:
            return

        # Deselect previous selection for this question
        for b in self.query(Button):
            if getattr(b, "_q_idx", None) == q_idx:
                b.remove_class("selected")

        # Select this one
        btn.add_class("selected")
        self._answers[q_idx] = (label_text, desc)

        # Show submit button if all questions answered
        if len(self._answers) >= len(self._questions):
            try:
                submit_btn = self.query_one("#auq-submit", Button)
                submit_btn.add_class("visible")
            except Exception:
                pass

    def _do_submit(self) -> None:
        """Build the combined answer string and post Submitted."""
        parts: list[str] = []
        for q_idx in sorted(self._answers.keys()):
            label, desc = self._answers[q_idx]
            q = self._questions[q_idx] if q_idx < len(self._questions) else {}
            header = q.get("header", f"Q{q_idx + 1}")
            if desc:
                parts.append(f"{header}: {label} — {desc}")
            else:
                parts.append(f"{header}: {label}")
        answer_text = "\n".join(parts)
        self.post_message(self.Submitted(answer_text))
