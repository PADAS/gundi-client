import importlib

import pytest

from gundi_client_v2 import settings as settings_module


@pytest.fixture(autouse=True)
def _restore_settings_after_test():
    """Reload settings after each test so the module state reflects the env
    that pytest's monkeypatch fixture has restored, not the test's patched env."""
    yield
    importlib.reload(settings_module)


def _isolate_envfile(monkeypatch, tmp_path):
    """Point GUNDI_CLIENT_ENVFILE at an empty file so environs.read_env() during
    importlib.reload doesn't re-merge a developer's local .env."""
    empty = tmp_path / "empty.env"
    empty.write_text("")
    monkeypatch.setenv("GUNDI_CLIENT_ENVFILE", str(empty))


def test_oauth_token_url_read_directly_from_env(monkeypatch, tmp_path):
    _isolate_envfile(monkeypatch, tmp_path)
    monkeypatch.setenv("OAUTH_TOKEN_URL", "https://idp.example.com/oauth/token")
    monkeypatch.delenv("OAUTH_ISSUER", raising=False)
    monkeypatch.delenv("KEYCLOAK_ISSUER", raising=False)
    reloaded = importlib.reload(settings_module)
    assert reloaded.OAUTH_TOKEN_URL == "https://idp.example.com/oauth/token"
    assert reloaded.OAUTH_ISSUER is None


def test_oauth_token_url_no_longer_derived_from_issuer(monkeypatch, tmp_path):
    _isolate_envfile(monkeypatch, tmp_path)
    monkeypatch.setenv("OAUTH_ISSUER", "https://idp.example.com/realms/x")
    monkeypatch.delenv("OAUTH_TOKEN_URL", raising=False)
    monkeypatch.delenv("KEYCLOAK_ISSUER", raising=False)
    reloaded = importlib.reload(settings_module)
    assert reloaded.OAUTH_ISSUER == "https://idp.example.com/realms/x"
    assert reloaded.OAUTH_TOKEN_URL is None


def test_dotenv_in_cwd_is_loaded(monkeypatch, tmp_path):
    """A `.env` in the current working directory is auto-loaded when
    GUNDI_CLIENT_ENVFILE is unset (environs' default resolves from the installed
    package dir, not the caller's cwd — so we must find it from cwd explicitly)."""
    monkeypatch.delenv("GUNDI_CLIENT_ENVFILE", raising=False)
    monkeypatch.delenv("GUNDI_API_BASE_URL", raising=False)
    (tmp_path / ".env").write_text(
        "GUNDI_API_BASE_URL=https://from-cwd-dotenv.example\n"
    )
    monkeypatch.chdir(tmp_path)
    reloaded = importlib.reload(settings_module)
    assert reloaded.GUNDI_API_BASE_URL == "https://from-cwd-dotenv.example"


def test_dotenv_found_by_walking_up_from_cwd(monkeypatch, tmp_path):
    """The `.env` is discovered by walking up from cwd, like other dotenv tools,
    so running from a subdirectory of the project still picks it up."""
    monkeypatch.delenv("GUNDI_CLIENT_ENVFILE", raising=False)
    monkeypatch.delenv("GUNDI_API_BASE_URL", raising=False)
    (tmp_path / ".env").write_text("GUNDI_API_BASE_URL=https://from-parent.example\n")
    subdir = tmp_path / "nested" / "deeper"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)
    reloaded = importlib.reload(settings_module)
    assert reloaded.GUNDI_API_BASE_URL == "https://from-parent.example"


def test_envfile_overrides_cwd_dotenv(monkeypatch, tmp_path):
    """GUNDI_CLIENT_ENVFILE takes precedence over a `.env` in the cwd."""
    monkeypatch.delenv("GUNDI_API_BASE_URL", raising=False)
    (tmp_path / ".env").write_text("GUNDI_API_BASE_URL=https://from-cwd.example\n")
    explicit = tmp_path / "explicit.env"
    explicit.write_text("GUNDI_API_BASE_URL=https://from-envfile.example\n")
    monkeypatch.setenv("GUNDI_CLIENT_ENVFILE", str(explicit))
    monkeypatch.chdir(tmp_path)
    reloaded = importlib.reload(settings_module)
    assert reloaded.GUNDI_API_BASE_URL == "https://from-envfile.example"
