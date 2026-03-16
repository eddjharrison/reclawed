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
    text = "Options:\na. Keep it simple\nb. Add more features"
    choices = detect_choices(text)
    assert len(choices) == 2
    assert choices[0] == ("a", "Keep it simple")
    assert choices[1] == ("b", "Add more features")


def test_lettered_with_parenthesis():
    text = "a) Option one\nb) Option two"
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
