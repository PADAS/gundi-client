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
    config_store.save_config(
        {"active": "prod", "environments": {"prod": {"base_url": "u"}}}
    )
    assert config_store.load_config() == {
        "active": "prod",
        "environments": {"prod": {"base_url": "u"}},
    }


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


def test_add_get_environment():
    config_store.add_environment("dev", {"base_url": "u", "client_id": "c"})
    assert config_store.get_environment("dev") == {"base_url": "u", "client_id": "c"}


def test_add_first_environment_does_not_auto_activate():
    config_store.add_environment("dev", {"base_url": "u"})
    assert config_store.get_active() is None


def test_get_unknown_environment_raises():
    with pytest.raises(config_store.ConfigError):
        config_store.get_environment("nope")


def test_set_active_requires_existing():
    with pytest.raises(config_store.ConfigError):
        config_store.set_active("ghost")


def test_set_and_get_active():
    config_store.add_environment("prod", {"base_url": "u"})
    config_store.set_active("prod")
    assert config_store.get_active() == "prod"


def test_list_environments():
    config_store.add_environment("a", {"base_url": "u"})
    config_store.add_environment("b", {"base_url": "u"})
    assert set(config_store.list_environments()) == {"a", "b"}


def test_remove_environment_clears_active_when_removed():
    config_store.add_environment("a", {"base_url": "u"})
    config_store.set_active("a")
    config_store.remove_environment("a")
    assert "a" not in config_store.list_environments()
    assert config_store.get_active() is None


def test_remove_unknown_raises():
    with pytest.raises(config_store.ConfigError):
        config_store.remove_environment("nope")


def test_load_config_non_object_raises_config_error():
    config_store.config_dir().mkdir(parents=True, exist_ok=True)
    config_store.config_file().write_text("[1, 2, 3]")
    with pytest.raises(config_store.ConfigError):
        config_store.load_config()


def test_add_environment_rejects_unsafe_name():
    with pytest.raises(config_store.ConfigError):
        config_store.add_environment("../evil", {"base_url": "u", "client_id": "c"})


def test_save_config_tightens_preexisting_permissions():
    config_store.ensure_dir(config_store.config_dir())
    path = config_store.config_file()
    path.write_text("{}")
    os.chmod(path, 0o644)
    config_store.save_config({"active": None, "environments": {}})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_load_config_bad_active_type_raises():
    config_store.config_dir().mkdir(parents=True, exist_ok=True)
    config_store.config_file().write_text('{"active": {"x": 1}, "environments": {}}')
    with pytest.raises(config_store.ConfigError):
        config_store.load_config()


def test_load_config_bad_environments_type_raises():
    config_store.config_dir().mkdir(parents=True, exist_ok=True)
    config_store.config_file().write_text('{"active": null, "environments": [1, 2]}')
    with pytest.raises(config_store.ConfigError):
        config_store.load_config()
