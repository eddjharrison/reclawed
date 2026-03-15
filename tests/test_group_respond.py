"""Tests for group chat Claude response control.

Covers:
- Config field loading and validation
- ChatScreen._is_mentioned (all pattern variants)
- action_cycle_respond_mode cycling order
- StatusBar group mode badge
- Config TOML loading of group_auto_respond
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reclawed.config import Config
from reclawed.models import Session
from reclawed.store import Store
from reclawed.widgets.status_bar import StatusBar


# ---------------------------------------------------------------------------
# Config — group_auto_respond field
# ---------------------------------------------------------------------------

class TestConfigGroupAutoRespond:
    def test_default_is_own(self):
        cfg = Config()
        assert cfg.group_auto_respond == "own"

    def test_valid_values_accepted(self):
        for mode in ("own", "mentions", "all", "off"):
            cfg = Config(group_auto_respond=mode)
            assert cfg.group_auto_respond == mode

    def test_invalid_value_falls_back_to_own(self):
        cfg = Config(group_auto_respond="bogus")
        assert cfg.group_auto_respond == "own"

    def test_load_from_toml(self, tmp_path: Path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('group_auto_respond = "mentions"\n', encoding="utf-8")
        cfg = Config.load(config_path=toml_file)
        assert cfg.group_auto_respond == "mentions"

    def test_load_from_toml_invalid_falls_back(self, tmp_path: Path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('group_auto_respond = "unknown"\n', encoding="utf-8")
        cfg = Config.load(config_path=toml_file)
        assert cfg.group_auto_respond == "own"

    def test_load_from_toml_all_modes(self, tmp_path: Path):
        for mode in ("own", "mentions", "all", "off"):
            toml_file = tmp_path / f"config_{mode}.toml"
            toml_file.write_text(f'group_auto_respond = "{mode}"\n', encoding="utf-8")
            cfg = Config.load(config_path=toml_file)
            assert cfg.group_auto_respond == mode, f"Failed for mode={mode}"

    def test_missing_key_uses_default(self, tmp_path: Path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text("relay_port = 9999\n", encoding="utf-8")
        cfg = Config.load(config_path=toml_file)
        assert cfg.group_auto_respond == "own"


# ---------------------------------------------------------------------------
# ChatScreen._is_mentioned — unit tests without spinning up the full TUI
# ---------------------------------------------------------------------------

def _make_is_mentioned(name: str):
    """Return a bound _is_mentioned callable with the given participant name.

    We avoid instantiating ChatScreen (which requires a running Textual app)
    by building a minimal stand-in that just carries the config attribute and
    calls the real method logic via an unbound call.
    """
    # Import here so the module is loaded after any fixture setup
    from reclawed.screens.chat import ChatScreen

    cfg = Config(participant_name=name)
    store = Store(":memory:")
    # We need a session in the store for ChatScreen.__init__
    session = Session(name="Test")
    store.create_session(session)

    # Patch the Textual Screen __init__ to avoid DOM setup
    with patch.object(ChatScreen, "on_mount", lambda self: None):
        # Build the object without running the app
        obj = object.__new__(ChatScreen)
        obj.store = store
        obj.config = cfg
        obj.session = session
        obj._claude = MagicMock()
        obj._sending = False
        obj._selected_model = None
        obj._relay_client = None
        obj._relay_server = None
        obj._tunnel_proc = None
        obj._relay_receive_task = None
        obj._group_respond_mode = "mentions"

    return obj._is_mentioned


class TestIsMentioned:
    """Tests for the @mention pattern matching logic."""

    def setup_method(self):
        self._check = _make_is_mentioned("Ed")

    def test_full_form_exact(self):
        assert self._check("@Ed's Claude what do you think?")

    def test_full_form_case_insensitive_name(self):
        assert self._check("@ed's claude please respond")

    def test_full_form_case_insensitive_claude(self):
        assert self._check("@Ed's CLAUDE hey")

    def test_full_form_mixed_case(self):
        assert self._check("@ED'S Claude !")

    def test_short_form_exact(self):
        assert self._check("@Ed what's your take?")

    def test_short_form_case_insensitive(self):
        assert self._check("@ed can you help?")

    def test_short_form_word_boundary(self):
        # "@Eddie" should NOT match "@Ed"
        check = _make_is_mentioned("Ed")
        assert not check("@Eddie please respond")

    def test_short_form_at_end_of_string(self):
        assert self._check("Hey @Ed")

    def test_no_mention(self):
        assert not self._check("Hey everyone, what do you think?")

    def test_name_not_preceded_by_at(self):
        assert not self._check("Ed's Claude is great")

    def test_mention_of_different_name(self):
        assert not self._check("@Alice's Claude, thoughts?")

    def test_name_with_spaces(self):
        check = _make_is_mentioned("Alice Bob")
        assert check("@Alice Bob's Claude, what do you think?")

    def test_name_with_special_regex_chars(self):
        # Dot in name should be escaped, not treated as regex wildcard
        check = _make_is_mentioned("Dr.Smith")
        assert check("@Dr.Smith's Claude please")
        assert not check("@DrXSmith's Claude please")

    def test_full_form_with_extra_whitespace(self):
        # The pattern uses \s+ between "name's" and "claude"
        assert self._check("@Ed's  Claude  what's up?")

    def test_mention_embedded_in_sentence(self):
        assert self._check("I was wondering if @Ed's Claude could weigh in here.")

    def test_multiple_mentions_in_message(self):
        # Only our name matters
        assert self._check("@Bob go first, then @Ed what do you think?")


# ---------------------------------------------------------------------------
# ChatScreen.RESPOND_MODES cycling order
# ---------------------------------------------------------------------------

class TestRespondModeCycle:
    def test_cycle_order(self):
        from reclawed.screens.chat import ChatScreen
        modes = ChatScreen.RESPOND_MODES
        assert modes == ["own", "mentions", "all", "off"]

    def test_cycle_wraps_around(self):
        from reclawed.screens.chat import ChatScreen
        modes = ChatScreen.RESPOND_MODES
        # Starting from last ("off") should wrap to first ("own")
        idx = modes.index("off")
        next_mode = modes[(idx + 1) % len(modes)]
        assert next_mode == "own"

    def test_all_modes_covered(self):
        from reclawed.screens.chat import ChatScreen
        assert set(ChatScreen.RESPOND_MODES) == {"own", "mentions", "all", "off"}


# ---------------------------------------------------------------------------
# StatusBar — group mode badge
# ---------------------------------------------------------------------------

class TestStatusBarGroupMode:
    def _make_bar(self) -> StatusBar:
        """Instantiate StatusBar without a running Textual app."""
        bar = object.__new__(StatusBar)
        bar._session_name = "Test"
        bar._model = ""
        bar._cost = 0.0
        bar._message_count = 0
        bar._streaming_indicator = None
        bar._group_mode = None
        # Patch update() so we can inspect the rendered string
        bar._last_render = ""
        bar.update = lambda text: setattr(bar, "_last_render", text)
        return bar

    def test_no_group_mode_by_default(self):
        bar = self._make_bar()
        bar._refresh_display()
        assert "[" not in bar._last_render

    def test_group_mode_shown_when_set(self):
        bar = self._make_bar()
        bar.update_info(group_mode="mentions")
        assert "[mentions]" in bar._last_render

    def test_group_mode_cleared(self):
        bar = self._make_bar()
        bar.update_info(group_mode="all")
        assert "[all]" in bar._last_render
        bar.update_info(clear_group_mode=True)
        assert "[" not in bar._last_render

    def test_group_mode_cycles_through_all_values(self):
        bar = self._make_bar()
        for mode in ("own", "mentions", "all", "off"):
            bar.update_info(group_mode=mode)
            assert f"[{mode}]" in bar._last_render, f"Expected [{mode}] in status bar"

    def test_none_group_mode_does_not_clear_existing(self):
        bar = self._make_bar()
        bar.update_info(group_mode="all")
        # Passing group_mode=None should leave the existing badge unchanged
        bar.update_info(group_mode=None)
        assert "[all]" in bar._last_render

    def test_group_mode_badge_position_before_streaming(self):
        bar = self._make_bar()
        bar.update_info(group_mode="own")
        bar._streaming_indicator = "Claude is thinking..."
        bar._refresh_display()
        render = bar._last_render
        # Badge should appear before the streaming indicator
        assert render.index("[own]") < render.index("Claude is thinking...")
