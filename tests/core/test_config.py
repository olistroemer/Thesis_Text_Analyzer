"""tta.toml round-trip tests (SDD §5.4)."""

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
