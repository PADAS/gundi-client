"""GundiClient behaviour with the shared token cache."""

import asyncio
import logging

import httpx
import pytest
import respx
from fakeredis import FakeAsyncRedis

from gundi_client_v2 import settings
from gundi_client_v2.client import GundiClient
from gundi_client_v2.errors import TokenCacheConfigError
from gundi_client_v2.token_cache import (
    FileTokenCache,
    MemoryTokenCache,
    RedisTokenCache,
    TokenStore,
    clear_token_cache,
)


def test_client_defaults_to_memory_only(client_settings):
    client = GundiClient(**client_settings)
    assert isinstance(client._token_store, TokenStore)
    assert client._token_store._backend is None


def test_client_builds_the_backend_from_the_kwarg_url(client_settings, tmp_path):
    client = GundiClient(**client_settings, token_cache_url=f"file://{tmp_path}")
    assert isinstance(client._token_store._backend, FileTokenCache)


def test_client_reads_the_url_from_settings(client_settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "GUNDI_TOKEN_CACHE_URL", f"file://{tmp_path}")
    client = GundiClient(**client_settings)
    assert isinstance(client._token_store._backend, FileTokenCache)


def test_injected_token_cache_wins_over_the_url(client_settings, tmp_path):
    injected = RedisTokenCache(client=FakeAsyncRedis(decode_responses=True))
    client = GundiClient(
        **client_settings, token_cache_url=f"file://{tmp_path}", token_cache=injected
    )
    assert client._token_store._backend is injected


def test_bad_url_fails_at_construction(client_settings):
    with pytest.raises(TokenCacheConfigError):
        GundiClient(**client_settings, token_cache_url="memcached://nope")
