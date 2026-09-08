import json
from datetime import datetime, timedelta, timezone

import pytest

from gundi_client_v2.token_cache import NO_REFRESH, CachedToken

NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)


def _token(**overrides) -> CachedToken:
    fields = dict(
        access_token="access-1",
        refresh_token="refresh-1",
        token_type="Bearer",
        expires_at=NOW + timedelta(hours=1),
        refresh_expires_at=NOW + timedelta(hours=10),
    )
    fields.update(overrides)
    return CachedToken(**fields)


def test_liveness_uses_absolute_timestamps():
    token = _token()
    assert token.is_live(NOW)
    assert not token.is_live(NOW + timedelta(hours=2))
    assert token.refresh_is_live(NOW + timedelta(hours=2))
    assert not token.refresh_is_live(NOW + timedelta(hours=11))


def test_no_refresh_token_is_never_refresh_live():
    token = _token(refresh_token="", refresh_expires_at=NO_REFRESH)
    assert not token.refresh_is_live(NOW)


def test_to_oauth_token_zeroes_relative_lifetimes():
    oauth = _token().to_oauth_token()
    assert oauth.access_token == "access-1"
    assert oauth.refresh_token == "refresh-1"
    assert oauth.token_type == "Bearer"
    assert oauth.expires_in == 0
    assert oauth.refresh_expires_in == 0


def test_json_round_trip():
    token = _token()
    restored = CachedToken.from_json(token.to_json())
    assert restored == token
    payload = json.loads(token.to_json())
    assert set(payload) == {
        "access_token",
        "refresh_token",
        "token_type",
        "expires_at",
        "refresh_expires_at",
    }


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        json.dumps({"access_token": ""}),
        json.dumps(
            {
                "access_token": "a",
                "expires_at": "yesterday",
                "refresh_expires_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        json.dumps(
            {
                "access_token": "a",
                "expires_at": "2026-01-01T00:00:00",
                "refresh_expires_at": "2026-01-01T00:00:00+00:00",
            }
        ),  # naive timestamp
    ],
)
def test_from_json_returns_none_for_malformed_input(text):
    assert CachedToken.from_json(text) is None


def test_from_json_defaults_optional_fields():
    text = json.dumps(
        {
            "access_token": "a",
            "expires_at": "2026-01-01T00:00:00+00:00",
            "refresh_expires_at": "2026-01-01T00:00:00+00:00",
        }
    )
    token = CachedToken.from_json(text)
    assert token.refresh_token == ""
    assert token.token_type == "Bearer"
