import pytest
from typer.testing import CliRunner

from gundi_client_v2.cli import app, config_store

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    return tmp_path


def test_env_add_stores_environment():
    result = runner.invoke(
        app,
        [
            "env",
            "add",
            "prod",
            "--base-url",
            "https://api.x",
            "--client-id",
            "c",
            "--issuer",
            "https://auth.x",
        ],
    )
    assert result.exit_code == 0, result.output
    env = config_store.get_environment("prod")
    assert env == {
        "base_url": "https://api.x",
        "client_id": "c",
        "issuer": "https://auth.x",
    }


def test_env_add_requires_issuer_or_token_url():
    result = runner.invoke(
        app, ["env", "add", "prod", "--base-url", "u", "--client-id", "c"]
    )
    assert result.exit_code == 2, result.output
    assert "--issuer" in result.output


def test_env_add_activate_sets_active():
    runner.invoke(
        app,
        [
            "env",
            "add",
            "prod",
            "--base-url",
            "u",
            "--client-id",
            "c",
            "--issuer",
            "i",
            "--activate",
        ],
    )
    assert config_store.get_active() == "prod"


def test_env_use_and_list_marks_active():
    runner.invoke(
        app, ["env", "add", "a", "--base-url", "u", "--client-id", "c", "--issuer", "i"]
    )
    runner.invoke(
        app, ["env", "add", "b", "--base-url", "u", "--client-id", "c", "--issuer", "i"]
    )
    runner.invoke(app, ["env", "use", "b"])
    result = runner.invoke(app, ["env", "list"])
    assert result.exit_code == 0
    assert "* b" in result.output
    assert "  a" in result.output


def test_env_use_unknown_exits_2():
    result = runner.invoke(app, ["env", "use", "ghost"])
    assert result.exit_code == 2
    assert "unknown environment" in result.output


def test_env_show_outputs_config():
    runner.invoke(
        app,
        ["env", "add", "prod", "--base-url", "u", "--client-id", "c", "--issuer", "i"],
    )
    result = runner.invoke(app, ["env", "show", "prod"])
    assert result.exit_code == 0
    assert "base_url" in result.output


def test_env_remove_deletes():
    runner.invoke(
        app,
        ["env", "add", "prod", "--base-url", "u", "--client-id", "c", "--issuer", "i"],
    )
    result = runner.invoke(app, ["env", "remove", "prod"])
    assert result.exit_code == 0
    assert "prod" not in config_store.get_environments()


def test_env_list_corrupt_config_exits_2():
    # A hand-corrupted config.json must fail cleanly (exit 2), not traceback.
    config_store.config_dir().mkdir(parents=True, exist_ok=True)
    config_store.config_file().write_text("{not json")
    result = runner.invoke(app, ["env", "list"])
    assert result.exit_code == 2, result.output
    assert "Error" in result.output


def test_env_add_rejects_unsafe_name():
    result = runner.invoke(
        app,
        [
            "env",
            "add",
            "../evil",
            "--base-url",
            "u",
            "--client-id",
            "c",
            "--issuer",
            "i",
        ],
    )
    assert result.exit_code == 2, result.output
    assert "invalid environment name" in result.output


def test_env_list_dangling_active_exits_2():
    # Stored active points at a non-existent environment (hand-edited config).
    config_store.save_config(
        {
            "active": "ghost",
            "environments": {"prod": {"base_url": "u", "client_id": "c"}},
        }
    )
    result = runner.invoke(app, ["env", "list"])
    assert result.exit_code == 2, result.output
    assert "Traceback" not in result.output
