import asyncio
import json
import logging
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
    TokenStore,
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


def test_to_oauth_token_reports_remaining_lifetimes(clock):
    oauth = _token().to_oauth_token()
    assert oauth.access_token == "access-1"
    assert oauth.refresh_token == "refresh-1"
    assert oauth.token_type == "Bearer"
    # Relative to the moment it is read, not to the moment it was issued.
    assert oauth.expires_in == 3600
    assert oauth.refresh_expires_in == 36000

    clock["now"] = NOW + timedelta(hours=2)  # access dead, refresh still live
    later = _token().to_oauth_token()
    assert later.expires_in == 0
    assert later.refresh_expires_in == 8 * 3600

    # An explicit ``now`` wins over the module clock.
    assert _token().to_oauth_token(NOW).expires_in == 3600


def test_to_oauth_token_reports_no_refresh_lifetime_without_a_refresh_token(clock):
    oauth = _token(refresh_token="", refresh_expires_at=NO_REFRESH).to_oauth_token()
    assert oauth.refresh_token == ""
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


def _stamped(**fields) -> str:
    """A serialized token whose timestamps are valid, so only ``fields`` is at fault."""
    payload = {
        "expires_at": "2026-01-01T00:00:00+00:00",
        "refresh_expires_at": "2026-01-01T00:00:00+00:00",
    }
    payload.update(fields)
    return json.dumps(payload)


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
        _stamped(access_token=["x"]),  # not a string
        _stamped(access_token=12345),  # not a string
        _stamped(access_token="a\r\nX: 1"),  # header-splitting characters
        _stamped(access_token="a\x00b"),  # NUL
        _stamped(access_token="a", token_type={"k": "v"}),  # not a string
        _stamped(access_token="a", refresh_token=["r"]),  # not a string
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


@pytest.mark.asyncio
async def test_memory_cache_lock_is_per_key():
    # lock() needs a running loop: the lock it returns is bound to it.
    cache = MemoryTokenCache()
    assert cache.lock("a") is cache.lock("a")
    assert cache.lock("a") is not cache.lock("b")
    assert isinstance(cache.lock("a"), asyncio.Lock)


def test_memory_cache_lock_is_rebuilt_for_a_new_event_loop():
    """Two asyncio.run calls are two loops; each must get its own lock."""
    cache = MemoryTokenCache()

    async def take_lock():
        lock = cache.lock("a")
        assert cache._locks["a"][0] is asyncio.get_running_loop()
        return lock

    first = asyncio.run(take_lock())
    second = asyncio.run(take_lock())
    assert first is not second


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
    # A directory left behind by something else must not keep serving tokens
    # world-readable: the first write tightens an existing directory to 0700.
    directory = tmp_path / "tokens"
    directory.mkdir()
    os.chmod(directory, 0o777)
    cache = FileTokenCache(directory)
    key = KEY_PREFIX + "cd" * 16
    await cache.set(key, _token())
    assert stat.S_IMODE(os.stat(directory).st_mode) == 0o700
    assert (
        stat.S_IMODE(os.stat(tmp_path / "tokens" / ("cd" * 16 + ".json")).st_mode)
        == 0o600
    )


@pytest.mark.asyncio
async def test_file_cache_creates_a_private_directory(tmp_path, clock):
    """The directory the first write creates is 0700 from the start."""
    directory = tmp_path / "tokens"
    cache = FileTokenCache(directory)
    await cache.set(KEY_PREFIX + "12" * 16, _token())
    assert stat.S_IMODE(os.stat(directory).st_mode) == 0o700


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


class _Flaky:
    """A TokenCache whose every call raises."""

    def __init__(self):
        self.calls = 0

    async def get(self, key):
        self.calls += 1
        raise ConnectionError("redis down")

    async def set(self, key, token):
        self.calls += 1
        raise ConnectionError("redis down")

    async def delete(self, key):
        self.calls += 1
        raise ConnectionError("redis down")


@pytest.mark.asyncio
async def test_store_reads_memory_before_the_backend(fake_redis, clock):
    backend = RedisTokenCache(client=fake_redis)
    store = TokenStore(backend, memory=MemoryTokenCache())
    await store.set("k", _token())
    await fake_redis.delete("k")  # backend lost it; memory still answers
    assert await store.get("k") == _token()


@pytest.mark.asyncio
async def test_store_copies_a_backend_hit_into_memory(fake_redis, clock):
    backend = RedisTokenCache(client=fake_redis)
    await backend.set("k", _token())
    memory = MemoryTokenCache()
    store = TokenStore(backend, memory=memory)
    assert await store.get("k") == _token()
    assert await memory.get("k") == _token()


@pytest.mark.asyncio
async def test_store_delete_reaches_both_layers(fake_redis, clock):
    backend = RedisTokenCache(client=fake_redis)
    memory = MemoryTokenCache()
    store = TokenStore(backend, memory=memory)
    await store.set("k", _token())
    await store.delete("k")
    assert await memory.get("k") is None
    assert await fake_redis.exists("k") == 0


@pytest.mark.asyncio
async def test_store_without_a_backend_is_memory_only(clock):
    store = TokenStore(None, memory=MemoryTokenCache())
    await store.set("k", _token())
    assert await store.get("k") == _token()


@pytest.mark.asyncio
async def test_store_contains_backend_failures_and_warns_once_per_streak(clock, caplog):
    flaky = _Flaky()
    store = TokenStore(flaky, memory=MemoryTokenCache())
    key = KEY_PREFIX + "ab" * 16
    token = _token(access_token="access-secret-value")
    with caplog.at_level(logging.WARNING, logger="gundi_client_v2.token_cache"):
        assert await store.get(key) is None
        await store.set(key, token)
        assert await store.get(key) == token  # memory still serves
        await store.delete(key)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "_Flaky" in message
    assert "ConnectionError" in message
    assert "redis down" not in message  # no exception text
    assert "ab" * 16 not in message  # no key
    assert "access-secret-value" not in message  # no token
    assert (
        flaky.calls == 3
    )  # get, set, delete all attempted; the memory hit made no backend call


@pytest.mark.asyncio
async def test_stores_sharing_a_backend_share_one_failure_streak(clock, caplog):
    """The runner builds a TokenStore per GundiClient per call; during an outage
    that must not mean a warning per call."""
    flaky = _Flaky()
    with caplog.at_level(logging.WARNING, logger="gundi_client_v2.token_cache"):
        for _ in range(5):
            await TokenStore(flaky, memory=MemoryTokenCache()).get("k")
    assert sum(r.levelno == logging.WARNING for r in caplog.records) == 1


@pytest.mark.asyncio
async def test_store_warns_again_after_the_backend_recovers_and_fails_again(
    clock, caplog, fake_redis
):
    class Toggle:
        def __init__(self):
            self.fail = True
            self.inner = RedisTokenCache(client=fake_redis)

        async def get(self, key):
            if self.fail:
                raise TimeoutError()
            return await self.inner.get(key)

        async def set(self, key, token):
            if self.fail:
                raise TimeoutError()
            await self.inner.set(key, token)

        async def delete(self, key):
            if self.fail:
                raise TimeoutError()
            await self.inner.delete(key)

    toggle = Toggle()
    store = TokenStore(toggle, memory=MemoryTokenCache())
    with caplog.at_level(logging.WARNING, logger="gundi_client_v2.token_cache"):
        await store.get("a")  # fails: warning 1
        await store.get("b")  # fails: suppressed
        toggle.fail = False
        await store.get("c")  # succeeds: streak reset
        toggle.fail = True
        await store.get("d")  # fails: warning 2
    assert sum(r.levelno == logging.WARNING for r in caplog.records) == 2
