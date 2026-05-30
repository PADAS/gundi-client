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
