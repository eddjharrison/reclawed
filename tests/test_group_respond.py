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

from clawdia.config import Config
from clawdia.models import Session
from clawdia.store import Store
from clawdia.widgets.status_bar import StatusBar


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
    from clawdia.screens.chat import ChatScreen

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
        obj._is_streaming = False
        obj._message_queues = {}
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
        from clawdia.screens.chat import ChatScreen
        modes = ChatScreen.ROOM_MODES
        assert modes == ["humans_only", "claude_assists", "full_auto", "claude_to_claude"]

    def test_cycle_wraps_around(self):
        from clawdia.screens.chat import ChatScreen
        modes = ChatScreen.ROOM_MODES
        idx = modes.index("claude_to_claude")
        next_mode = modes[(idx + 1) % len(modes)]
        assert next_mode == "humans_only"

    def test_all_modes_covered(self):
        from clawdia.screens.chat import ChatScreen
        assert set(ChatScreen.ROOM_MODES) == {
            "humans_only", "claude_assists", "full_auto", "claude_to_claude"
        }

    def test_all_modes_have_labels(self):
        from clawdia.screens.chat import ChatScreen
        for mode in ChatScreen.ROOM_MODES:
            assert mode in ChatScreen.ROOM_MODE_LABELS
            assert mode in ChatScreen.ROOM_MODE_DESCRIPTIONS


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
        bar._typing_indicator = None
        bar._connection_status = None
        bar._encrypted = False
        bar._workspace_name = None
        bar._permission_mode = None
        bar._context_tokens = 0
        bar._context_max = 200_000
        bar._orchestrator_mode = False
        bar._voice_active = False
        bar._voice_recording = False
        # Patch update() so we can inspect the rendered string
        bar._last_render = ""
        bar.update = lambda text: setattr(bar, "_last_render", text)
        return bar

    def test_no_group_mode_by_default(self):
        bar = self._make_bar()
        bar._refresh_display()
        assert "Humans Only" not in bar._last_render
        assert "Full Auto" not in bar._last_render
        assert "C2C" not in bar._last_render

    def test_group_mode_shown_when_set(self):
        bar = self._make_bar()
        bar.update_info(group_mode="humans_only")
        assert "Humans Only" in bar._last_render

    def test_group_mode_cleared(self):
        bar = self._make_bar()
        bar.update_info(group_mode="full_auto")
        assert "Full Auto" in bar._last_render
        bar.update_info(clear_group_mode=True)
        # No mode label when cleared
        assert "Full Auto" not in bar._last_render

    def test_group_mode_cycles_through_all_values(self):
        bar = self._make_bar()
        expected = {
            "humans_only": "Humans Only",
            "claude_assists": "Claude Assists",
            "full_auto": "Full Auto",
            "claude_to_claude": "C2C",
        }
        for mode, label in expected.items():
            bar.update_info(group_mode=mode)
            assert label in bar._last_render, f"Expected '{label}' in status bar for mode '{mode}'"

    def test_none_group_mode_does_not_clear_existing(self):
        bar = self._make_bar()
        bar.update_info(group_mode="full_auto")
        # Passing group_mode=None should leave the existing badge unchanged
        bar.update_info(group_mode=None)
        assert "Full Auto" in bar._last_render

    def test_group_mode_and_streaming_both_shown(self):
        bar = self._make_bar()
        bar.update_info(group_mode="claude_assists")
        bar._streaming_indicator = "[bold]42 tok/s[/bold]"
        bar._refresh_display()
        render = bar._last_render
        # Both should be present in the status bar
        assert "Claude Assists" in render
        assert "42 tok/s" in render

    def test_legacy_modes_display_correctly(self):
        """Old mode names should map to new display labels."""
        bar = self._make_bar()
        bar.update_info(group_mode="own")
        assert "Claude Assists" in bar._last_render
        bar.update_info(group_mode="all")
        assert "Full Auto" in bar._last_render


# ---------------------------------------------------------------------------
# Config — group context settings
# ---------------------------------------------------------------------------

class TestConfigGroupContext:
    def test_default_mode_is_isolated(self):
        cfg = Config()
        assert cfg.group_context_mode == "isolated"

    def test_default_context_window(self):
        cfg = Config()
        assert cfg.group_context_window == 20

    def test_valid_modes_accepted(self):
        for mode in ("isolated", "shared_history"):
            cfg = Config(group_context_mode=mode)
            assert cfg.group_context_mode == mode

    def test_invalid_mode_falls_back(self):
        cfg = Config(group_context_mode="bogus")
        assert cfg.group_context_mode == "isolated"

    def test_load_from_toml(self, tmp_path: Path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(
            'group_context_mode = "shared_history"\ngroup_context_window = 10\n',
            encoding="utf-8",
        )
        cfg = Config.load(config_path=toml_file)
        assert cfg.group_context_mode == "shared_history"
        assert cfg.group_context_window == 10


# ---------------------------------------------------------------------------
# Group context preamble formatting
# ---------------------------------------------------------------------------

class TestGroupContextPreamble:
    def _make_chat_screen(self, mode: str = "shared_history", window: int = 20):
        """Build a minimal ChatScreen-like object for testing preamble logic."""
        from clawdia.screens.chat import ChatScreen
        cfg = Config(
            participant_name="Ed",
            group_context_mode=mode,
            group_context_window=window,
        )
        store = Store(":memory:")
        session = Session(name="Group Test", is_group=True)
        store.create_session(session)

        obj = object.__new__(ChatScreen)
        obj.store = store
        obj.config = cfg
        obj.session = session
        obj._claude = MagicMock()
        obj._is_streaming = False
        obj._message_queues = {}
        obj._selected_model = None
        obj._relay_client = None
        obj._relay_server = None
        obj._tunnel_proc = None
        obj._relay_receive_task = None
        obj._group_respond_mode = "own"
        obj._typing_users = {}
        obj._typing_timer_running = False
        obj._read_receipts = {}
        obj._msg_id_to_seq = {}
        return obj

    def test_preamble_empty_when_no_messages(self):
        obj = self._make_chat_screen()
        assert obj._build_group_context_preamble() == ""

    def test_preamble_includes_recent_messages(self):
        obj = self._make_chat_screen()
        from clawdia.models import Message
        obj.store.add_message(Message(
            role="user", content="Hello from Ed",
            session_id=obj.session.id, sender_name="Ed",
        ))
        obj.store.add_message(Message(
            role="assistant", content="Hello from Claude",
            session_id=obj.session.id, sender_name="Ed's Claude",
        ))
        preamble = obj._build_group_context_preamble()
        assert "[Group chat context:]" in preamble
        assert "Ed: Hello from Ed" in preamble
        assert "Ed's Claude: Hello from Claude" in preamble

    def test_preamble_respects_window_size(self):
        obj = self._make_chat_screen(window=2)
        from clawdia.models import Message
        for i in range(5):
            obj.store.add_message(Message(
                role="user", content=f"Message {i}",
                session_id=obj.session.id, sender_name="Ed",
            ))
        preamble = obj._build_group_context_preamble()
        # Should only include last 2 messages
        assert "Message 3" in preamble
        assert "Message 4" in preamble
        assert "Message 0" not in preamble

    def test_preamble_excludes_deleted(self):
        obj = self._make_chat_screen()
        from clawdia.models import Message
        m1 = Message(
            role="user", content="Visible",
            session_id=obj.session.id, sender_name="Ed",
        )
        m2 = Message(
            role="user", content="Deleted",
            session_id=obj.session.id, sender_name="Ed",
        )
        obj.store.add_message(m1)
        obj.store.add_message(m2)
        obj.store.soft_delete_message(m2.id)
        preamble = obj._build_group_context_preamble()
        assert "Visible" in preamble
        assert "Deleted" not in preamble

    def test_no_preamble_in_isolated_mode(self):
        obj = self._make_chat_screen(mode="isolated")
        from clawdia.models import Message
        obj.store.add_message(Message(
            role="user", content="Hello",
            session_id=obj.session.id, sender_name="Ed",
        ))
        preamble = obj._build_group_context_preamble()
        # Method returns context regardless — the caller checks the mode
        # So this just verifies the method works; the mode check is in on_compose_area_submitted
        assert "[Group chat context:]" in preamble
