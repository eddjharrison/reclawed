"""Tests for choice detection regex."""

from reclawed.utils import detect_choices


def test_numbered_choices():
    text = "Pick one:\n1. Use React\n2. Use Vue\n3. Use Svelte"
    choices = detect_choices(text)
    assert len(choices) == 3
    assert choices[0] == ("1", "Use React")
    assert choices[1] == ("2", "Use Vue")
    assert choices[2] == ("3", "Use Svelte")


def test_lettered_choices():
    text = "Which do you prefer?\na. Keep it simple\nb. Add more features"
    choices = detect_choices(text)
    assert len(choices) == 2
    assert choices[0] == ("a", "Keep it simple")
    assert choices[1] == ("b", "Add more features")


def test_lettered_with_parenthesis():
    text = "Choose one:\na) Option one\nb) Option two"
    choices = detect_choices(text)
    assert len(choices) == 2


def test_single_item_not_detected():
    text = "1. This is just a list item"
    assert detect_choices(text) == []


def test_no_choices():
    text = "Just a regular paragraph with no numbered items."
    assert detect_choices(text) == []


def test_mixed_content():
    text = "Here are your options:\n\n1. Create a new file\n2. Edit the existing one\n\nLet me know."
    choices = detect_choices(text)
    assert len(choices) == 2
    assert choices[0][0] == "1"
    assert choices[1][0] == "2"


def test_empty_text():
    assert detect_choices("") == []


def test_plain_numbered_list_not_detected():
    """Regular numbered lists without a decision signal should NOT show buttons."""
    text = "The fix adds two handlers:\n\n1. App regains terminal focus\n2. Screen resumes from a modal"
    assert detect_choices(text) == []


def test_too_many_items_not_detected():
    """More than 6 items is likely a list, not choices."""
    text = "Which do you prefer?\n" + "\n".join(f"{i}. Item {i}" for i in range(1, 9))
    assert detect_choices(text) == []


def test_question_signal_triggers_detection():
    text = "Would you like me to:\n1. Refactor the code\n2. Add tests\n3. Write docs"
    choices = detect_choices(text)
    assert len(choices) == 3
