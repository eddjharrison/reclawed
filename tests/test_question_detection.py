"""Tests for question detection heuristic."""

from reclawed.utils import detect_question


def test_simple_question():
    assert detect_question("What do you think?") is True


def test_multi_paragraph_question():
    text = "Here's the code.\n\nDoes this look correct?"
    assert detect_question(text) is True


def test_not_a_question():
    assert detect_question("Here is the result.") is False


def test_code_block_ending():
    text = "Here's the fix:\n```python\nprint('hello')\n```"
    assert detect_question(text) is False


def test_empty_text():
    assert detect_question("") is False


def test_question_with_trailing_whitespace():
    assert detect_question("What should I do?   ") is True


def test_statement_with_question_in_middle():
    text = "You asked: why?\n\nHere's the answer."
    assert detect_question(text) is False
