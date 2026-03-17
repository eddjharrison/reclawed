"""Tests for config parsing, workspaces, and workspace_for_cwd."""

from pathlib import Path

from reclawed.config import Config, Workspace


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
