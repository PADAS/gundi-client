import json
import os
import stat

import pytest

from gundi_client_v2.cli import config_store


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def test_config_dir_under_xdg(tmp_path):
    assert config_store.config_dir() == tmp_path / "gundi"


def test_load_config_missing_returns_empty():
    assert config_store.load_config() == {"active": None, "environments": {}}


def test_save_then_load_round_trips():
    config_store.save_config({"active": "prod", "environments": {"prod": {"base_url": "u"}}})
    assert config_store.load_config() == {"active": "prod", "environments": {"prod": {"base_url": "u"}}}


def test_save_config_sets_0600_and_dir_0700(tmp_path):
    config_store.save_config({"active": None, "environments": {}})
    cfg = config_store.config_file()
    assert stat.S_IMODE(cfg.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "gundi").stat().st_mode) == 0o700


def test_load_config_corrupt_raises_config_error():
    config_store.config_dir().mkdir(parents=True)
    config_store.config_file().write_text("{not json")
    with pytest.raises(config_store.ConfigError):
        config_store.load_config()
