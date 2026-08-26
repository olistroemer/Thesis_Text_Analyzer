"""tta.toml round-trip tests (SDD Sec. 5.4)."""

from tta.core.config import Config, load_config, save_config


def test_missing_file_yields_defaults(tmp_path):
    config = load_config(tmp_path)
    assert config.workers is None
    assert config.ui_mode == "basic"
    assert config.outlier_scheme == "default"
    assert config.institution is None


def test_round_trip(tmp_path):
    save_config(tmp_path, Config(workers=4, ui_mode="extended", institution="FH Wedel"))
    config = load_config(tmp_path)
    assert config.workers == 4
    assert config.ui_mode == "extended"
    assert config.institution == "FH Wedel"


def test_unknown_keys_survive_round_trip(tmp_path):
    (tmp_path / "tta.toml").write_text(
        "[future_section]\nknob = 7\n\n[ui]\nmode = \"extended\"\n", encoding="utf-8"
    )
    config = load_config(tmp_path)
    save_config(tmp_path, config)
    reloaded = load_config(tmp_path)
    assert reloaded.raw["future_section"]["knob"] == 7
    assert reloaded.ui_mode == "extended"


def test_invalid_mode_falls_back_to_basic(tmp_path):
    (tmp_path / "tta.toml").write_text("[ui]\nmode = \"hacker\"\n", encoding="utf-8")
    assert load_config(tmp_path).ui_mode == "basic"


def test_last_opened_pointer_round_trips(tmp_path):
    """The last-project pointer is a project file, not ~/.config state
    (SDD Sec. 5.6.1, US-PROF-NO-TRACES)."""
    save_config(tmp_path, Config(last_opened="/srv/theses"))
    assert load_config(tmp_path).last_opened == "/srv/theses"
    assert 'last_opened = "/srv/theses"' in (tmp_path / "tta.toml").read_text(encoding="utf-8")


def test_clearing_last_opened_removes_the_key(tmp_path):
    save_config(tmp_path, Config(last_opened="/srv/theses"))
    save_config(tmp_path, Config(last_opened=None))
    assert load_config(tmp_path).last_opened is None
    assert "last_opened" not in (tmp_path / "tta.toml").read_text(encoding="utf-8")


def test_last_opened_coexists_with_institution(tmp_path):
    save_config(tmp_path, Config(institution="FH Wedel", last_opened="/srv/theses"))
    reloaded = load_config(tmp_path)
    assert reloaded.institution == "FH Wedel"
    assert reloaded.last_opened == "/srv/theses"


def test_non_string_last_opened_is_ignored(tmp_path):
    (tmp_path / "tta.toml").write_text("[project]\nlast_opened = 7\n", encoding="utf-8")
    assert load_config(tmp_path).last_opened is None
