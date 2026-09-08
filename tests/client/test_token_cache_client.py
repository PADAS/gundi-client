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


TOKEN_URL = "https://fakeauth.com/auth/realms/dev/protocol/openid-connect/token"


def _mock_token_endpoint(mock, auth_token_response):
    return mock.post(TOKEN_URL).respond(status_code=200, json=auth_token_response)


@pytest.mark.asyncio
async def test_two_clients_with_the_same_credentials_share_one_token(
    client_settings, auth_token_response
):
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        first = GundiClient(**client_settings)
        second = GundiClient(**client_settings)
        h1 = await first.get_auth_header()
        h2 = await second.get_auth_header()
    assert h1 == h2
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_concurrent_first_requests_in_one_process_make_one_token_request(
    client_settings, auth_token_response
):
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        clients = [GundiClient(**client_settings) for _ in range(10)]
        headers = await asyncio.gather(*(c.get_auth_header() for c in clients))
    assert len({h["authorization"] for h in headers}) == 1
    assert route.call_count == 1


def test_a_second_event_loop_reuses_the_lock_without_crashing(
    client_settings, auth_token_response, monkeypatch
):
    """A process that runs several event loops over its life (a worker that calls
    asyncio.run per job) must not trip over a per-key asyncio.Lock bound to the
    first loop that contended it."""
    from datetime import timedelta

    from gundi_client_v2 import token_cache as tc

    base = tc._now()
    clock = {"now": base}
    monkeypatch.setattr(tc, "_now", lambda: clock["now"])

    async def one_loop():
        async with respx.mock as mock:
            route = mock.post(TOKEN_URL)

            async def slow(request):
                await asyncio.sleep(0)  # suspend so the lock is really contended
                return httpx.Response(200, json=auth_token_response)

            route.side_effect = slow
            clients = [GundiClient(**client_settings) for _ in range(5)]
            await asyncio.gather(*(c.get_auth_header() for c in clients))
            return route.call_count

    assert asyncio.run(one_loop()) == 1
    # No clear_token_cache(): the entry (and its lock) survive into the next loop.
    # Age it so the second loop misses on the access token and fetches again.
    clock["now"] = base + timedelta(seconds=auth_token_response["expires_in"] + 60)
    assert asyncio.run(one_loop()) == 1


@pytest.mark.asyncio
async def test_different_secret_gets_its_own_token(
    client_settings, auth_token_response
):
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        await GundiClient(**client_settings).get_auth_header()
        rotated = {**client_settings, "keycloak_client_secret": "rotated-secret"}
        await GundiClient(**rotated).get_auth_header()
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_the_cached_token_carries_its_remaining_lifetime(
    client_settings, auth_token_response
):
    """``client.cached_token.expires_in`` is what callers read to decide how long
    a token is good for; it must be the time left, not zero."""
    buffered = auth_token_response["expires_in"] - 15  # the clock-skew buffer
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        first = GundiClient(**client_settings)
        await first.get_auth_header()
        assert buffered - 5 <= first.cached_token.expires_in <= buffered
        assert first.cached_token.refresh_expires_in > 0
        second = GundiClient(**client_settings)  # served from the shared cache
        await second.get_auth_header()
    assert route.call_count == 1
    assert buffered - 5 <= second.cached_token.expires_in <= buffered
    assert second.cached_token.refresh_expires_in > 0


@pytest.mark.asyncio
async def test_a_fresh_process_finds_the_token_in_the_backend(
    client_settings, auth_token_response
):
    backend = RedisTokenCache(client=FakeAsyncRedis(decode_responses=True))
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        await GundiClient(**client_settings, token_cache=backend).get_auth_header()
        clear_token_cache()  # simulate a new process: empty memory, same Redis
        await GundiClient(**client_settings, token_cache=backend).get_auth_header()
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_a_fresh_process_finds_the_token_in_the_file_backend(
    client_settings, auth_token_response, tmp_path
):
    url = f"file://{tmp_path}/tokens"
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        await GundiClient(**client_settings, token_cache_url=url).get_auth_header()
        clear_token_cache()
        await GundiClient(**client_settings, token_cache_url=url).get_auth_header()
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_a_process_that_lost_its_memory_layer_re_authenticates_fully(
    client_settings, auth_token_response, monkeypatch
):
    """Memory-only deployment: after the access token expires and the process
    layer is gone, there is no refresh token to use, so it is a full
    authentication. The refresh-grant path is pinned by the backend test below."""
    from datetime import timedelta
    from gundi_client_v2 import token_cache as tc
    from urllib.parse import parse_qs

    base = tc._now()
    clock = {"now": base}
    monkeypatch.setattr(tc, "_now", lambda: clock["now"])
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        await GundiClient(**client_settings).get_auth_header()
        clock["now"] = base + timedelta(seconds=auth_token_response["expires_in"] + 60)
        clear_token_cache()
        await GundiClient(**client_settings).get_auth_header()
    grants = [
        parse_qs(c.request.content.decode())["grant_type"][0] for c in route.calls
    ]
    assert grants == ["client_credentials", "client_credentials"]


@pytest.mark.asyncio
async def test_refresh_grant_is_used_when_the_backend_holds_a_live_refresh_token(
    client_settings, auth_token_response, monkeypatch
):
    from datetime import timedelta
    from gundi_client_v2 import token_cache as tc
    from urllib.parse import parse_qs

    base = tc._now()
    clock = {"now": base}
    monkeypatch.setattr(tc, "_now", lambda: clock["now"])
    backend = RedisTokenCache(client=FakeAsyncRedis(decode_responses=True))
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        await GundiClient(**client_settings, token_cache=backend).get_auth_header()
        clock["now"] = base + timedelta(seconds=auth_token_response["expires_in"] + 60)
        clear_token_cache()
        await GundiClient(**client_settings, token_cache=backend).get_auth_header()
    grants = [
        parse_qs(c.request.content.decode())["grant_type"][0] for c in route.calls
    ]
    assert grants == ["client_credentials", "refresh_token"]


@pytest.mark.asyncio
async def test_a_malformed_backend_value_is_a_miss_and_is_deleted(
    client_settings, auth_token_response
):
    """A Redis value whose access_token is not a string must never reach
    OAuthToken: it is a miss, the key is deleted, and the client authenticates."""
    import json
    from datetime import timedelta

    from gundi_client_v2 import token_cache as tc

    fake = FakeAsyncRedis(decode_responses=True)
    deleted = []
    real_delete = fake.delete

    async def tracking_delete(*keys):
        deleted.extend(keys)
        return await real_delete(*keys)

    fake.delete = tracking_delete
    backend = RedisTokenCache(client=fake)
    client = GundiClient(**client_settings, token_cache=backend)
    key = client._token_cache_key(client_settings["oauth_token_url"])
    now = tc._now()
    await fake.set(
        key,
        json.dumps(
            {
                "access_token": ["not", "a", "string"],
                "refresh_token": "r",
                "token_type": "Bearer",
                "expires_at": (now + timedelta(hours=1)).isoformat(),
                "refresh_expires_at": (now + timedelta(hours=10)).isoformat(),
            }
        ),
    )
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        header = await client.get_auth_header()
    assert route.call_count == 1
    assert header["authorization"].startswith("Bearer ")
    assert deleted == [key]  # the malformed value was removed
    stored = await fake.get(key)  # and replaced by the freshly fetched token
    assert json.loads(stored)["access_token"] == auth_token_response["access_token"]


@pytest.mark.asyncio
async def test_force_refresh_evicts_the_shared_entry_before_re_authenticating(
    client_settings, auth_token_response
):
    fake = FakeAsyncRedis(decode_responses=True)
    backend = RedisTokenCache(client=fake)
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        client = GundiClient(**client_settings, token_cache=backend)
        await client.get_auth_header()
        keys_before = await fake.keys("gundi-client:token:*")
        # Make the eviction observable: the re-issued token differs.
        route.respond(
            status_code=200, json={**auth_token_response, "access_token": "second"}
        )
        await client.get_auth_header(force_refresh_token=True)
        keys_after = await fake.keys("gundi-client:token:*")
        stored = await fake.get(keys_after[0])
    assert keys_before == keys_after
    assert '"access_token": "second"' in stored
    assert route.call_count == 2
    # And a sibling client in the same process now sees the new token, not the rejected one.
    sibling = GundiClient(**client_settings, token_cache=backend)
    async with respx.mock as mock:
        _mock_token_endpoint(mock, auth_token_response)
        header = await sibling.get_auth_header()
    assert header["authorization"] == "Bearer second"


@pytest.mark.asyncio
async def test_unreachable_backend_degrades_to_memory_with_one_warning(
    client_settings, auth_token_response, caplog
):
    class Down:
        async def get(self, key):
            raise ConnectionError()

        async def set(self, key, token):
            raise ConnectionError()

        async def delete(self, key):
            raise ConnectionError()

    down = Down()  # the memoized backend every client built from one URL would share
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        with caplog.at_level(logging.WARNING, logger="gundi_client_v2.token_cache"):
            await GundiClient(**client_settings, token_cache=down).get_auth_header()
            await GundiClient(**client_settings, token_cache=down).get_auth_header()
    assert route.call_count == 1  # memory still shared the token
    assert sum(r.levelno == logging.WARNING for r in caplog.records) == 1


@pytest.mark.asyncio
async def test_the_302_login_redirect_still_retries_with_a_fresh_token(
    auth_token_response, gundi_client_v2
):
    """Regression guard: the existing redirect retry path goes through force_refresh_token."""
    from gundi_core.schemas.v2 import IntegrationType

    payload = {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "name": "Test Integration",
        "value": "test_integration",
        "description": "",
        "actions": [],
    }
    async with respx.mock(assert_all_called=True) as mock:
        token_route = mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=200, json=auth_token_response
        )
        type_url = f"{gundi_client_v2.integrations_endpoint}/types/"
        mock.post(type_url).side_effect = [
            httpx.Response(
                status_code=302,
                headers={
                    "location": "https://cdip-auth.pamdas.org/auth/realms/x/protocol/openid-connect/auth"
                },
            ),
            httpx.Response(status_code=200, json=payload),
        ]
        result = await gundi_client_v2.register_integration_type(payload)
    assert result == IntegrationType.parse_obj(payload)
    assert token_route.call_count == 2


def test_public_exports_and_version():
    import gundi_client_v2

    assert gundi_client_v2.__version__ == "3.7.0"
    assert gundi_client_v2.TokenCacheConfigError is TokenCacheConfigError
    from gundi_client_v2 import token_cache

    assert token_cache.MemoryTokenCache is MemoryTokenCache
