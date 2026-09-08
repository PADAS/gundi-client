import asyncio
import json
import math
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fakeredis import FakeAsyncRedis

from gundi_client_v2 import token_cache as tc
from gundi_client_v2.errors import GundiClientError, TokenCacheConfigError
from gundi_client_v2.token_cache import (
    KEY_PREFIX,
    NO_REFRESH,
    CachedToken,
    FileTokenCache,
    MemoryTokenCache,
    RedisTokenCache,
    clear_token_cache,
    token_cache_from_url,
    token_cache_key,
)

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


_KEY_ARGS = dict(
    token_url="https://auth.example/realms/dev/protocol/openid-connect/token",
    grant_type="client_credentials",
    client_id="runner",
    username=None,
    audience="portal",
    scope="openid",
    secret="s3cret",
)


def test_key_is_prefixed_hex_and_stable():
    key = token_cache_key(**_KEY_ARGS)
    assert key.startswith(KEY_PREFIX)
    digest = key[len(KEY_PREFIX) :]
    assert len(digest) == 32 and int(digest, 16) >= 0
    assert key == token_cache_key(**_KEY_ARGS)


def test_key_never_contains_the_secret_or_client_id():
    key = token_cache_key(**_KEY_ARGS)
    assert "s3cret" not in key
    assert "runner" not in key


@pytest.mark.parametrize(
    "change",
    [
        {"secret": "rotated"},
        {"client_id": "other"},
        {"token_url": "https://auth.example/realms/prod/protocol/openid-connect/token"},
        {"grant_type": "password", "username": "alice"},
        {"audience": "other-portal"},
        {"scope": "openid email"},
    ],
)
def test_key_changes_when_any_credential_component_changes(change):
    assert token_cache_key(**{**_KEY_ARGS, **change}) != token_cache_key(**_KEY_ARGS)


def test_key_treats_none_and_empty_alike():
    assert token_cache_key(**{**_KEY_ARGS, "audience": None}) == token_cache_key(
        **{**_KEY_ARGS, "audience": ""}
    )


@pytest.fixture
def clock(monkeypatch):
    state = {"now": NOW}
    monkeypatch.setattr(tc, "_now", lambda: state["now"])
    return state


@pytest.mark.asyncio
async def test_memory_cache_round_trip(clock):
    cache = MemoryTokenCache()
    assert await cache.get("k") is None
    await cache.set("k", _token())
    assert await cache.get("k") == _token()
    await cache.delete("k")
    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_memory_cache_keeps_an_entry_whose_refresh_token_is_still_live(clock):
    cache = MemoryTokenCache()
    await cache.set("k", _token())
    clock["now"] = NOW + timedelta(hours=2)  # access expired, refresh live
    assert await cache.get("k") == _token()


@pytest.mark.asyncio
async def test_memory_cache_drops_an_entry_whose_tokens_have_both_expired(clock):
    cache = MemoryTokenCache()
    await cache.set("k", _token())
    clock["now"] = NOW + timedelta(hours=11)
    assert await cache.get("k") is None
    assert "k" not in cache._entries


def test_memory_cache_lock_is_per_key():
    cache = MemoryTokenCache()
    assert cache.lock("a") is cache.lock("a")
    assert cache.lock("a") is not cache.lock("b")
    assert isinstance(cache.lock("a"), asyncio.Lock)


@pytest.mark.asyncio
async def test_clear_token_cache_empties_the_process_layer():
    await tc._PROCESS_CACHE.set("k", _token())
    clear_token_cache()
    assert await tc._PROCESS_CACHE.get("k") is None
    assert tc._PROCESS_CACHE._locks == {}


@pytest.mark.asyncio
async def test_file_cache_round_trip_and_layout(tmp_path, clock):
    cache = FileTokenCache(tmp_path / "tokens")
    key = KEY_PREFIX + "ab" * 16
    assert await cache.get(key) is None
    await cache.set(key, _token())
    assert await cache.get(key) == _token()
    files = list((tmp_path / "tokens").iterdir())
    assert [f.name for f in files] == ["ab" * 16 + ".json"]
    await cache.delete(key)
    assert await cache.get(key) is None
    await cache.delete(key)  # deleting a missing entry is not an error


@pytest.mark.asyncio
async def test_file_cache_permissions(tmp_path, clock):
    cache = FileTokenCache(tmp_path / "tokens")
    key = KEY_PREFIX + "cd" * 16
    await cache.set(key, _token())
    assert stat.S_IMODE(os.stat(tmp_path / "tokens").st_mode) == 0o700
    assert (
        stat.S_IMODE(os.stat(tmp_path / "tokens" / ("cd" * 16 + ".json")).st_mode)
        == 0o600
    )


@pytest.mark.asyncio
async def test_file_cache_write_is_atomic_and_leaves_no_temp_file(
    tmp_path, clock, monkeypatch
):
    cache = FileTokenCache(tmp_path / "tokens")
    key = KEY_PREFIX + "ef" * 16
    await cache.set(key, _token(access_token="first"))

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError):
        await cache.set(key, _token(access_token="second"))
    monkeypatch.undo()
    assert (await cache.get(key)).access_token == "first"
    assert [f.name for f in (tmp_path / "tokens").iterdir()] == ["ef" * 16 + ".json"]


@pytest.mark.asyncio
async def test_file_cache_treats_corrupt_and_expired_files_as_misses_and_removes_them(
    tmp_path, clock
):
    cache = FileTokenCache(tmp_path / "tokens")
    key = KEY_PREFIX + "01" * 16
    await cache.set(key, _token())
    path = tmp_path / "tokens" / ("01" * 16 + ".json")
    path.write_text("{not json")
    assert await cache.get(key) is None
    assert not path.exists()

    await cache.set(key, _token())
    clock["now"] = NOW + timedelta(hours=11)
    assert await cache.get(key) is None
    assert not path.exists()


def test_file_cache_accepts_a_string_directory(tmp_path):
    cache = FileTokenCache(str(tmp_path / "tokens"))
    assert cache.directory == tmp_path / "tokens"


@pytest.fixture
def fake_redis():
    return FakeAsyncRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_redis_cache_round_trip(fake_redis, clock):
    cache = RedisTokenCache(client=fake_redis)
    key = KEY_PREFIX + "aa" * 16
    assert await cache.get(key) is None
    await cache.set(key, _token())
    assert await cache.get(key) == _token()
    assert await fake_redis.exists(key) == 1
    await cache.delete(key)
    assert await cache.get(key) is None


@pytest.mark.asyncio
async def test_redis_cache_sets_ttl_to_the_later_expiry(fake_redis, clock):
    cache = RedisTokenCache(client=fake_redis)
    key = KEY_PREFIX + "bb" * 16
    await cache.set(key, _token())  # refresh lives 10 h, access 1 h
    ttl = await fake_redis.ttl(key)
    assert 10 * 3600 - 2 <= ttl <= 10 * 3600


@pytest.mark.asyncio
async def test_redis_cache_skips_writing_an_already_expired_token(fake_redis, clock):
    cache = RedisTokenCache(client=fake_redis)
    key = KEY_PREFIX + "cc" * 16
    clock["now"] = NOW + timedelta(hours=11)
    await cache.set(key, _token())
    assert await fake_redis.exists(key) == 0


@pytest.mark.asyncio
async def test_redis_cache_treats_a_corrupt_value_as_a_miss_and_deletes_it(
    fake_redis, clock
):
    cache = RedisTokenCache(client=fake_redis)
    key = KEY_PREFIX + "dd" * 16
    await fake_redis.set(key, "{oops")
    assert await cache.get(key) is None
    assert await fake_redis.exists(key) == 0


def test_redis_cache_requires_exactly_one_of_url_or_client(fake_redis):
    with pytest.raises(TokenCacheConfigError):
        RedisTokenCache()
    with pytest.raises(TokenCacheConfigError):
        RedisTokenCache(url="redis://localhost/2", client=fake_redis)


def test_redis_cache_without_the_redis_package_fails_at_construction(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_redis(name, *args, **kwargs):
        if name == "redis" or name.startswith("redis."):
            raise ImportError("No module named 'redis'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_redis)
    with pytest.raises(TokenCacheConfigError, match=r"gundi-client-v2\[redis\]"):
        RedisTokenCache(url="redis://localhost:6379/2")


def test_token_cache_config_error_is_a_client_error():
    assert issubclass(TokenCacheConfigError, GundiClientError)


def test_token_cache_from_url_selects_the_backend(tmp_path):
    assert token_cache_from_url(None) is None
    assert token_cache_from_url("") is None
    assert isinstance(token_cache_from_url("redis://localhost:6379/2"), RedisTokenCache)
    assert isinstance(
        token_cache_from_url("rediss://localhost:6380/2"), RedisTokenCache
    )
    file_cache = token_cache_from_url(f"file://{tmp_path}/tokens")
    assert isinstance(file_cache, FileTokenCache)
    assert file_cache.directory == tmp_path / "tokens"


@pytest.mark.parametrize("url", ["memcached://x", "http://x", "file://", "redis"])
def test_token_cache_from_url_rejects_unsupported_urls(url):
    with pytest.raises(TokenCacheConfigError):
        token_cache_from_url(url)


def test_token_cache_from_url_returns_one_backend_per_url_per_process(tmp_path):
    a = token_cache_from_url("redis://localhost:6379/2")
    b = token_cache_from_url("redis://localhost:6379/2")
    c = token_cache_from_url("redis://localhost:6379/3")
    assert a is b and a is not c
    f1 = token_cache_from_url(f"file://{tmp_path}")
    assert token_cache_from_url(f"file://{tmp_path}") is f1
    clear_token_cache()
    assert token_cache_from_url("redis://localhost:6379/2") is not a


def test_redis_url_uses_a_short_socket_timeout(monkeypatch):
    captured = {}

    class FakeRedisModule:
        class asyncio:
            class Redis:
                @staticmethod
                def from_url(url, **kwargs):
                    captured.update(kwargs, url=url)
                    return object()

    monkeypatch.setattr(tc, "_import_redis", lambda: FakeRedisModule)
    RedisTokenCache(url="redis://h:1/2")
    assert captured["url"] == "redis://h:1/2"
    assert captured["socket_timeout"] == 1.0
    assert captured["socket_connect_timeout"] == 1.0
    assert captured["decode_responses"] is True
