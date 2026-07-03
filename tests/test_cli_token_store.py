import stat
from datetime import datetime, timedelta, timezone

import pytest

from gundi_client_v2.cli import token_store


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


class FakeToken:
    def __init__(self, access, refresh="r", token_type="Bearer"):
        self.access_token = access
        self.refresh_token = refresh
        self.token_type = token_type
        self.expires_in = 0
        self.refresh_expires_in = 0


class FakeClient:
    def __init__(self):
        self.cached_token = None
        self.cached_token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)


def _future(seconds):
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def test_save_then_load_round_trips():
    exp, rexp = _future(1800), _future(43200)
    token_store.save_token("prod", FakeToken("AT", "RT"), exp, rexp)
    data = token_store.load_token("prod")
    assert data["access_token"] == "AT"
    assert data["refresh_token"] == "RT"
    assert datetime.fromisoformat(data["expires_at"]) == exp


def test_token_file_is_0600():
    token_store.save_token("prod", FakeToken("AT"), _future(60), _future(60))
    assert stat.S_IMODE(token_store.token_file("prod").stat().st_mode) == 0o600


def test_tokens_dir_is_0700():
    token_store.save_token("prod", FakeToken("AT"), _future(60), _future(60))
    assert stat.S_IMODE(token_store.config_store.tokens_dir().stat().st_mode) == 0o700


def test_load_missing_returns_none():
    assert token_store.load_token("prod") is None


def test_load_corrupt_returns_none():
    token_store.config_store.ensure_dir(token_store.config_store.tokens_dir())
    token_store.token_file("prod").write_text("{bad")
    assert token_store.load_token("prod") is None


def test_delete_token():
    token_store.save_token("prod", FakeToken("AT"), _future(60), _future(60))
    assert token_store.delete_token("prod") is True
    assert token_store.load_token("prod") is None
    assert token_store.delete_token("prod") is False


def test_apply_to_client_restores_attributes():
    exp, rexp = _future(1800), _future(43200)
    token_store.save_token("prod", FakeToken("AT", "RT"), exp, rexp)
    client = FakeClient()
    token_store.apply_to_client(client, token_store.load_token("prod"))
    assert client.cached_token.access_token == "AT"
    assert client.cached_token_expires_at == exp
    assert client.cached_token_refresh_expires_at == rexp


def test_load_token_missing_required_field_returns_none():
    # Valid JSON but missing access_token -> treat as a miss, not a later crash.
    token_store.config_store.ensure_dir(token_store.config_store.tokens_dir())
    token_store.token_file("prod").write_text(
        '{"expires_at": "2026-01-01T00:00:00+00:00", '
        '"refresh_expires_at": "2026-01-01T00:00:00+00:00"}'
    )
    assert token_store.load_token("prod") is None


def test_load_token_bad_timestamp_returns_none():
    token_store.config_store.ensure_dir(token_store.config_store.tokens_dir())
    token_store.token_file("prod").write_text(
        '{"access_token": "AT", "expires_at": "not-a-date", '
        '"refresh_expires_at": "2026-01-01T00:00:00+00:00"}'
    )
    assert token_store.load_token("prod") is None


def test_load_token_non_object_returns_none():
    token_store.config_store.ensure_dir(token_store.config_store.tokens_dir())
    token_store.token_file("prod").write_text("[1, 2, 3]")
    assert token_store.load_token("prod") is None


def test_load_token_naive_timestamp_returns_none():
    # Naive expires_at would crash `auth status` comparing to now(utc); miss instead.
    token_store.config_store.ensure_dir(token_store.config_store.tokens_dir())
    token_store.token_file("prod").write_text(
        '{"access_token": "AT", "expires_at": "2026-01-01T00:00:00", '
        '"refresh_expires_at": "2026-01-01T00:00:00"}'
    )
    assert token_store.load_token("prod") is None


def test_apply_to_client_coerces_null_optional_fields():
    # An explicit JSON null for refresh_token/token_type must not blow up
    # OAuthToken construction; coerce to safe defaults.
    exp = _future(60)
    data = {
        "access_token": "AT",
        "refresh_token": None,
        "token_type": None,
        "expires_at": exp.isoformat(),
        "refresh_expires_at": exp.isoformat(),
    }
    client = FakeClient()
    token_store.apply_to_client(client, data)  # must not raise
    assert client.cached_token.refresh_token == ""
    assert client.cached_token.token_type == "Bearer"
