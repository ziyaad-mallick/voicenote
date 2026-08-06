"""config.py: read/write ~/.voicenote/config.yaml, filling gaps from defaults.

CONFIG_PATH is redirected into tmp_path in every test so nothing here reads
or writes the real ~/.voicenote/config.yaml on the machine running the suite.
"""
from pathlib import Path

import pytest

import config


@pytest.fixture(autouse=True)
def _redirect_config_path(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.yaml")
    return tmp_path


def test_is_first_run_is_true_when_no_config_file_exists():
    assert config.is_first_run() is True


def test_is_first_run_is_false_once_a_config_file_exists():
    config.CONFIG_PATH.write_text("notes_dir: '~/x'\n")
    assert config.is_first_run() is False


def test_load_returns_defaults_when_no_config_file_exists():
    cfg = config.load()
    assert cfg["categories"] == config.get_default()["categories"]
    assert cfg["ollama"]["model"] == config.get_default()["ollama"]["model"]


def test_load_fills_missing_top_level_keys_from_defaults():
    config.CONFIG_PATH.write_text("notes_dir: '~/Documents/VoiceNotes'\n")
    cfg = config.load()
    assert "ollama" in cfg
    assert "whisper" in cfg
    assert cfg["whisper"]["backend"] == "vosk"


def test_load_does_not_clobber_a_value_present_in_the_file():
    config.CONFIG_PATH.write_text('categories: ["Work", "Life"]\n')
    cfg = config.load()
    assert cfg["categories"] == ["Work", "Life"]


def test_load_expands_notes_dir_into_a_path_object():
    config.CONFIG_PATH.write_text("notes_dir: '~/Documents/VoiceNotes'\n")
    cfg = config.load()
    assert isinstance(cfg["notes_dir"], Path)
    assert not str(cfg["notes_dir"]).startswith("~")


def test_save_then_load_round_trips_a_modified_value():
    cfg = config.get_default()
    cfg["categories"] = ["Solo Category"]
    config.save(cfg)

    reloaded = config.load()
    assert reloaded["categories"] == ["Solo Category"]


def test_save_writes_notes_dir_as_a_plain_string_not_a_path_object():
    cfg = config.get_default()
    cfg["notes_dir"] = Path.home() / "Documents" / "VoiceNotes"
    config.save(cfg)

    raw = config.CONFIG_PATH.read_text()
    assert "!!python" not in raw  # would appear if yaml had to tag a Path object
