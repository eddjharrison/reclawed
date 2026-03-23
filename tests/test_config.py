"""Tests for config parsing, workspaces, workspace_for_cwd, and worker templates."""

from pathlib import Path

from clawdia.config import BUILTIN_TEMPLATES, Config, Workspace, WorkerTemplate


def test_workspace_expanded_path(tmp_path):
    """expanded_path resolves ~ and returns an absolute path."""
    ws = Workspace(name="Test", path="~/some/project")
    assert ws.expanded_path == str(Path.home() / "some" / "project")


def test_workspace_expanded_path_absolute(tmp_path):
    """expanded_path works with already-absolute paths."""
    ws = Workspace(name="Test", path=str(tmp_path / "myproject"))
    assert ws.expanded_path == str(tmp_path / "myproject")


def test_config_default_no_workspaces():
    """Default config has an empty workspaces list."""
    cfg = Config()
    assert cfg.workspaces == []


def test_config_load_workspaces(tmp_path):
    """Workspaces are parsed from [[workspaces]] TOML array."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[[workspaces]]\nname = "Project A"\npath = "~/projects/a"\n\n'
        '[[workspaces]]\nname = "Project B"\npath = "/abs/path/b"\n'
    )
    cfg = Config.load(config_path=config_file)
    assert len(cfg.workspaces) == 2
    assert cfg.workspaces[0].name == "Project A"
    assert cfg.workspaces[0].path == "~/projects/a"
    assert cfg.workspaces[1].name == "Project B"
    assert cfg.workspaces[1].path == "/abs/path/b"


def test_config_load_no_workspaces(tmp_path):
    """Config without workspaces section loads cleanly."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('theme = "dark"\n')
    cfg = Config.load(config_path=config_file)
    assert cfg.workspaces == []


def test_config_load_workspaces_skips_incomplete(tmp_path):
    """Workspace entries missing name or path are skipped."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[[workspaces]]\nname = "Good"\npath = "/good"\n\n'
        '[[workspaces]]\nname = "Missing path"\n\n'
        '[[workspaces]]\npath = "/missing-name"\n'
    )
    cfg = Config.load(config_path=config_file)
    assert len(cfg.workspaces) == 1
    assert cfg.workspaces[0].name == "Good"


def test_workspace_for_cwd_match(tmp_path):
    """workspace_for_cwd returns the matching workspace."""
    ws = Workspace(name="Proj", path=str(tmp_path / "proj"))
    cfg = Config(workspaces=[ws])
    result = cfg.workspace_for_cwd(str(tmp_path / "proj"))
    assert result is not None
    assert result.name == "Proj"


def test_workspace_for_cwd_no_match(tmp_path):
    """workspace_for_cwd returns None when no workspace matches."""
    ws = Workspace(name="Proj", path=str(tmp_path / "proj"))
    cfg = Config(workspaces=[ws])
    assert cfg.workspace_for_cwd(str(tmp_path / "other")) is None


def test_workspace_for_cwd_none():
    """workspace_for_cwd returns None for cwd=None."""
    ws = Workspace(name="Proj", path="/some/path")
    cfg = Config(workspaces=[ws])
    assert cfg.workspace_for_cwd(None) is None


def test_workspace_for_cwd_no_workspaces():
    """workspace_for_cwd returns None when no workspaces configured."""
    cfg = Config()
    assert cfg.workspace_for_cwd("/any/path") is None


def test_workspace_for_cwd_tilde_resolution():
    """workspace_for_cwd resolves ~ in both workspace path and cwd."""
    ws = Workspace(name="Home", path="~/myproject")
    cfg = Config(workspaces=[ws])
    result = cfg.workspace_for_cwd(str(Path.home() / "myproject"))
    assert result is not None
    assert result.name == "Home"


# --- Config.save() tests ---


def test_config_save_roundtrip(tmp_path):
    """save() then load() produces equivalent config."""
    cfg = Config(
        theme="monokai",
        participant_name="Ed",
        relay_port=9999,
        permission_mode="bypassPermissions",
    )
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    assert loaded.theme == "monokai"
    assert loaded.participant_name == "Ed"
    assert loaded.relay_port == 9999
    assert loaded.permission_mode == "bypassPermissions"


def test_config_save_with_workspaces(tmp_path):
    """save() persists workspaces as [[workspaces]] TOML array."""
    cfg = Config(workspaces=[
        Workspace(name="Project A", path="~/projects/a"),
        Workspace(name="Project B", path="/abs/b"),
    ])
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    assert len(loaded.workspaces) == 2
    assert loaded.workspaces[0].name == "Project A"
    assert loaded.workspaces[0].path == "~/projects/a"
    assert loaded.workspaces[1].name == "Project B"
    assert loaded.workspaces[1].path == "/abs/b"


def test_config_save_creates_parent_dirs(tmp_path):
    """save() creates parent directories if they don't exist."""
    config_file = tmp_path / "nested" / "dir" / "config.toml"
    cfg = Config(theme="light")
    cfg.save(config_path=config_file)
    assert config_file.exists()
    loaded = Config.load(config_path=config_file)
    assert loaded.theme == "light"


def test_config_save_escapes_special_chars(tmp_path):
    """save() correctly escapes quotes and backslashes in strings."""
    cfg = Config(participant_name='Ed "The Dev" Harrison')
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    assert loaded.participant_name == 'Ed "The Dev" Harrison'


def test_config_save_empty_workspaces(tmp_path):
    """save() with no workspaces produces valid TOML."""
    cfg = Config()
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    assert loaded.workspaces == []


# --- Relay mode tests ---


def test_config_default_relay_mode():
    """Default relay_mode is 'local'."""
    cfg = Config()
    assert cfg.relay_mode == "local"
    assert cfg.relay_url is None
    assert cfg.relay_token is None


def test_config_load_relay_mode_remote(tmp_path):
    """relay_mode, relay_url, relay_token are loaded from TOML."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'relay_mode = "remote"\n'
        'relay_url = "wss://relay.example.com"\n'
        'relay_token = "secret123"\n'
    )
    cfg = Config.load(config_path=config_file)
    assert cfg.relay_mode == "remote"
    assert cfg.relay_url == "wss://relay.example.com"
    assert cfg.relay_token == "secret123"


def test_config_save_roundtrip_relay_fields(tmp_path):
    """save() and load() preserve relay fields."""
    cfg = Config(
        relay_mode="remote",
        relay_url="wss://relay.company.com",
        relay_token="team-token",
    )
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    assert loaded.relay_mode == "remote"
    assert loaded.relay_url == "wss://relay.company.com"
    assert loaded.relay_token == "team-token"


def test_config_relay_mode_validation():
    """Invalid relay_mode falls back to 'local'."""
    cfg = Config(relay_mode="invalid")
    assert cfg.relay_mode == "local"


def test_config_save_local_mode_no_url(tmp_path):
    """Local mode doesn't write relay_url/relay_token if they're None."""
    cfg = Config(relay_mode="local")
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    content = config_file.read_text()
    assert "relay_url" not in content
    assert "relay_token" not in content
    loaded = Config.load(config_path=config_file)
    assert loaded.relay_mode == "local"
    assert loaded.relay_url is None


# --- Roundtrip tests for newly-exposed General tab fields ---


def test_config_save_roundtrip_auto_name_sessions_true(tmp_path):
    """auto_name_sessions=True round-trips through save/load."""
    cfg = Config(auto_name_sessions=True)
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    assert loaded.auto_name_sessions is True


def test_config_save_roundtrip_auto_name_sessions_false(tmp_path):
    """auto_name_sessions=False round-trips through save/load."""
    cfg = Config(auto_name_sessions=False)
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    assert loaded.auto_name_sessions is False


def test_config_save_roundtrip_max_quote_length(tmp_path):
    """max_quote_length round-trips through save/load."""
    cfg = Config(max_quote_length=500)
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    assert loaded.max_quote_length == 500


def test_config_save_roundtrip_max_quote_length_default(tmp_path):
    """Default max_quote_length (200) round-trips through save/load."""
    cfg = Config()
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    assert loaded.max_quote_length == 200


def test_config_save_roundtrip_data_dir(tmp_path):
    """data_dir round-trips through save/load."""
    custom_dir = tmp_path / "custom" / "data"
    cfg = Config(data_dir=custom_dir)
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    assert loaded.data_dir == custom_dir


def test_config_save_roundtrip_workspace_overrides(tmp_path):
    """Workspace per-workspace overrides (model, permission_mode, allowed_tools) round-trip."""
    cfg = Config(workspaces=[
        Workspace(
            name="Backend",
            path="/projects/backend",
            model="opus",
            permission_mode="bypassPermissions",
            allowed_tools="Read,Edit,Bash",
        ),
        Workspace(
            name="Frontend",
            path="/projects/frontend",
            # No overrides — should remain None after round-trip.
        ),
    ])
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    assert len(loaded.workspaces) == 2
    backend = loaded.workspaces[0]
    assert backend.model == "opus"
    assert backend.permission_mode == "bypassPermissions"
    assert backend.allowed_tools == "Read,Edit,Bash"
    frontend = loaded.workspaces[1]
    assert frontend.model is None
    assert frontend.permission_mode is None
    assert frontend.allowed_tools is None


# ---------------------------------------------------------------------------
# Worker Templates — dataclass defaults
# ---------------------------------------------------------------------------


def test_worker_template_defaults():
    """WorkerTemplate has expected default field values."""
    tmpl = WorkerTemplate(id="my-tmpl", name="My Template", system_prompt="Do stuff.")
    assert tmpl.model == "sonnet"
    assert tmpl.permission_mode == "bypassPermissions"
    assert tmpl.allowed_tools is None
    assert tmpl.builtin is False


def test_worker_template_custom_fields():
    """WorkerTemplate stores all custom field values."""
    tmpl = WorkerTemplate(
        id="reviewer",
        name="Code Reviewer",
        system_prompt="Review this code.",
        model="opus",
        permission_mode="acceptEdits",
        allowed_tools="Read,Glob,Grep",
        builtin=False,
    )
    assert tmpl.id == "reviewer"
    assert tmpl.name == "Code Reviewer"
    assert tmpl.system_prompt == "Review this code."
    assert tmpl.model == "opus"
    assert tmpl.permission_mode == "acceptEdits"
    assert tmpl.allowed_tools == "Read,Glob,Grep"
    assert tmpl.builtin is False


# ---------------------------------------------------------------------------
# Worker Templates — builtin merge logic
# ---------------------------------------------------------------------------


def test_builtin_templates_count():
    """BUILTIN_TEMPLATES contains exactly 4 entries."""
    assert len(BUILTIN_TEMPLATES) == 4


def test_builtin_templates_ids():
    """BUILTIN_TEMPLATES has the expected IDs."""
    ids = {t.id for t in BUILTIN_TEMPLATES}
    assert ids == {"implementation", "test-writer", "code-reviewer", "doc-writer"}


def test_builtin_templates_all_marked_builtin():
    """All BUILTIN_TEMPLATES have builtin=True."""
    for t in BUILTIN_TEMPLATES:
        assert t.builtin is True, f"{t.id} should have builtin=True"


def test_config_default_has_builtin_templates():
    """Default Config always includes the 4 built-in templates."""
    cfg = Config()
    builtin_ids = {t.id for t in cfg.worker_templates if t.builtin}
    assert builtin_ids == {"implementation", "test-writer", "code-reviewer", "doc-writer"}


def test_builtin_templates_appear_first():
    """Built-in templates come before custom ones in config.worker_templates."""
    custom = WorkerTemplate(id="my-custom", name="Custom", system_prompt="Do it.", builtin=False)
    cfg = Config(worker_templates=[custom])
    ids = [t.id for t in cfg.worker_templates]
    # All builtins should precede any custom template
    builtin_indices = [i for i, t in enumerate(cfg.worker_templates) if t.builtin]
    custom_indices = [i for i, t in enumerate(cfg.worker_templates) if not t.builtin]
    assert max(builtin_indices) < min(custom_indices)


def test_custom_templates_not_duplicated_with_builtins():
    """A custom template with the same ID as a builtin is ignored (builtin wins)."""
    impersonator = WorkerTemplate(
        id="implementation",  # same ID as a builtin
        name="Fake Implementation",
        system_prompt="I am a fake.",
        builtin=False,
    )
    cfg = Config(worker_templates=[impersonator])
    impl_templates = [t for t in cfg.worker_templates if t.id == "implementation"]
    assert len(impl_templates) == 1
    assert impl_templates[0].builtin is True  # the builtin wins


def test_builtin_templates_not_duplicated_on_reload(tmp_path):
    """Loading a config file twice doesn't duplicate built-in templates."""
    cfg = Config()
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    builtin_ids = [t.id for t in loaded.worker_templates if t.builtin]
    assert len(builtin_ids) == len(set(builtin_ids)), "Duplicate builtins after reload"


# ---------------------------------------------------------------------------
# Worker Templates — save / load round-trip
# ---------------------------------------------------------------------------


def test_custom_template_save_roundtrip(tmp_path):
    """A custom template survives save() → load() unchanged."""
    custom = WorkerTemplate(
        id="my-worker",
        name="My Worker",
        system_prompt="Do the thing.",
        model="haiku",
        permission_mode="default",
        builtin=False,
    )
    cfg = Config(worker_templates=[custom])
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    custom_loaded = [t for t in loaded.worker_templates if not t.builtin]
    assert len(custom_loaded) == 1
    t = custom_loaded[0]
    assert t.id == "my-worker"
    assert t.name == "My Worker"
    assert t.system_prompt == "Do the thing."
    assert t.model == "haiku"
    assert t.permission_mode == "default"
    assert t.allowed_tools is None
    assert t.builtin is False


def test_custom_template_with_allowed_tools_roundtrip(tmp_path):
    """allowed_tools field on custom templates survives save/load."""
    custom = WorkerTemplate(
        id="tool-user",
        name="Tool User",
        system_prompt="Use the tools.",
        allowed_tools="Read,Bash,Glob",
        builtin=False,
    )
    cfg = Config(worker_templates=[custom])
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    custom_loaded = [t for t in loaded.worker_templates if not t.builtin]
    assert len(custom_loaded) == 1
    assert custom_loaded[0].allowed_tools == "Read,Bash,Glob"


def test_custom_template_special_chars_in_prompt(tmp_path):
    """System prompts with quotes and newlines round-trip correctly."""
    custom = WorkerTemplate(
        id="special",
        name='Special "Chars"',
        system_prompt='Line one.\nLine two with "quotes".',
        builtin=False,
    )
    cfg = Config(worker_templates=[custom])
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    custom_loaded = [t for t in loaded.worker_templates if not t.builtin]
    assert len(custom_loaded) == 1
    assert custom_loaded[0].name == 'Special "Chars"'
    assert custom_loaded[0].system_prompt == 'Line one.\nLine two with "quotes".'


def test_multiple_custom_templates_roundtrip(tmp_path):
    """Multiple custom templates all survive save/load."""
    customs = [
        WorkerTemplate(id=f"tmpl-{i}", name=f"Template {i}", system_prompt=f"Prompt {i}.", builtin=False)
        for i in range(3)
    ]
    cfg = Config(worker_templates=customs)
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    custom_loaded = [t for t in loaded.worker_templates if not t.builtin]
    assert len(custom_loaded) == 3
    loaded_ids = {t.id for t in custom_loaded}
    assert loaded_ids == {"tmpl-0", "tmpl-1", "tmpl-2"}


def test_builtin_templates_not_persisted_to_toml(tmp_path):
    """save() does not write built-in templates to the TOML file."""
    cfg = Config()
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    content = config_file.read_text()
    # Built-in IDs must not appear in the saved TOML
    for builtin_id in ("implementation", "test-writer", "code-reviewer", "doc-writer"):
        assert builtin_id not in content, f"Built-in template '{builtin_id}' should not be in TOML"


def test_config_templates_skip_incomplete_entries(tmp_path):
    """Template entries missing id or name are skipped on load."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[[worker_templates]]\n'
        'id = "good"\nname = "Good Template"\nsystem_prompt = "Do it."\n\n'
        '[[worker_templates]]\n'
        'name = "Missing ID"\nsystem_prompt = "No id."\n\n'
        '[[worker_templates]]\n'
        'id = "missing-name"\nsystem_prompt = "No name."\n'
    )
    cfg = Config.load(config_path=config_file)
    custom = [t for t in cfg.worker_templates if not t.builtin]
    assert len(custom) == 1
    assert custom[0].id == "good"


def test_config_no_custom_templates_by_default(tmp_path):
    """A config file with no [[worker_templates]] section loads only builtins."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('theme = "dark"\n')
    cfg = Config.load(config_path=config_file)
    custom = [t for t in cfg.worker_templates if not t.builtin]
    assert custom == []


# ---------------------------------------------------------------------------
# Named tunnel config fields
# ---------------------------------------------------------------------------


def test_config_tunnel_fields_default_none():
    """Default config has no tunnel fields set."""
    cfg = Config()
    assert cfg.tunnel_name is None
    assert cfg.tunnel_uuid is None
    assert cfg.tunnel_hostname is None


def test_config_tunnel_fields_roundtrip(tmp_path):
    """Tunnel fields survive save/load."""
    cfg = Config(
        tunnel_name="clawdia-relay",
        tunnel_uuid="abc-123-def",
        tunnel_hostname="relay.example.com",
    )
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    loaded = Config.load(config_path=config_file)
    assert loaded.tunnel_name == "clawdia-relay"
    assert loaded.tunnel_uuid == "abc-123-def"
    assert loaded.tunnel_hostname == "relay.example.com"


def test_config_tunnel_fields_not_written_when_none(tmp_path):
    """Tunnel fields are omitted from TOML when None."""
    cfg = Config()
    config_file = tmp_path / "config.toml"
    cfg.save(config_path=config_file)
    content = config_file.read_text()
    assert "tunnel_name" not in content
    assert "tunnel_uuid" not in content
    assert "tunnel_hostname" not in content


def test_config_load_tunnel_fields(tmp_path):
    """Tunnel fields are loaded from TOML."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'tunnel_name = "my-tunnel"\n'
        'tunnel_uuid = "uuid-123"\n'
        'tunnel_hostname = "relay.test.com"\n'
    )
    cfg = Config.load(config_path=config_file)
    assert cfg.tunnel_name == "my-tunnel"
    assert cfg.tunnel_uuid == "uuid-123"
    assert cfg.tunnel_hostname == "relay.test.com"
