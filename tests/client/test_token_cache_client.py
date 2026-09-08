"""GundiClient behaviour with the shared token cache."""

import asyncio
import logging
import os

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


def _cache_warnings(caplog):
    """Warning records from this module only: caplog collects every logger's."""
    return [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and r.name == "gundi_client_v2.token_cache"
    ]


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
    assert len(_cache_warnings(caplog)) == 1


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory modes")
@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores directory permissions",
)
@pytest.mark.asyncio
async def test_a_read_only_file_directory_degrades_to_memory_with_one_warning(
    client_settings, auth_token_response, tmp_path, caplog
):
    """The spec's file-backend counterpart to an unreachable Redis: the call
    succeeds, one warning is logged, and the token is shared in memory only.

    The unwritable directory is the *parent*: FileTokenCache.set chmods its own
    directory to 0700 on every write (it must tighten a directory left behind
    with looser bits), which would undo a mode set on the directory itself.
    """
    read_only = tmp_path / "ro"
    read_only.mkdir()
    os.chmod(read_only, 0o500)
    url = f"file://{read_only}/tokens"
    try:
        async with respx.mock as mock:
            route = _mock_token_endpoint(mock, auth_token_response)
            with caplog.at_level(logging.WARNING, logger="gundi_client_v2.token_cache"):
                first = await GundiClient(
                    **client_settings, token_cache_url=url
                ).get_auth_header()
                second = await GundiClient(
                    **client_settings, token_cache_url=url
                ).get_auth_header()
        assert first == second
        assert route.call_count == 1  # the memory layer still shared the token
        assert not (read_only / "tokens").exists()
        assert len(_cache_warnings(caplog)) == 1
    finally:
        os.chmod(read_only, 0o700)  # let tmp_path cleanup remove it


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


def test_cache_key_separates_users_and_ignores_the_password(client_settings):
    """The password never enters the key: a human password hashed next to
    guessable material would make every key an offline password verifier. The
    username always does, even when no password is present (CLI profiles
    restore a token onto a client that knows the user but not the password)."""
    base = {k: v for k, v in client_settings.items() if k != "keycloak_client_secret"}
    url = client_settings["oauth_token_url"]
    alice_p1 = GundiClient(**base, username="alice", password="p1")._token_cache_key(
        url
    )
    alice_p2 = GundiClient(**base, username="alice", password="p2")._token_cache_key(
        url
    )
    bob_p1 = GundiClient(**base, username="bob", password="p1")._token_cache_key(url)
    alice_profile = GundiClient(**base, username="alice")._token_cache_key(url)
    bob_profile = GundiClient(**base, username="bob")._token_cache_key(url)
    assert alice_p1 == alice_p2
    assert alice_p1 != bob_p1
    assert alice_profile != bob_profile
    # client_credentials keeps the (high-entropy) secret in the key: rotation invalidates.
    cc1 = GundiClient(**client_settings)._token_cache_key(url)
    cc2 = GundiClient(
        **{**client_settings, "keycloak_client_secret": "rotated"}
    )._token_cache_key(url)
    assert cc1 != cc2


@pytest.mark.asyncio
async def test_force_refresh_adopts_a_siblings_replacement_instead_of_evicting_it(
    client_settings, auth_token_response
):
    """Two clients hold the same rejected token. The first evicts it and refreshes;
    the second must adopt that replacement, not evict it and replay the same
    refresh token (a replay is invalid_grant on rotating IdPs and can revoke the
    sibling's fresh token too)."""
    from urllib.parse import parse_qs

    responses = iter(["first", "second", "third"])

    def issue(request):
        return httpx.Response(
            200, json={**auth_token_response, "access_token": next(responses)}
        )

    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).mock(side_effect=issue)
        a = GundiClient(**client_settings)
        b = GundiClient(**client_settings)
        assert (await a.get_auth_header())["authorization"] == "Bearer first"
        assert (await b.get_auth_header())["authorization"] == "Bearer first"
        assert (await a.get_auth_header(force_refresh_token=True))[
            "authorization"
        ] == "Bearer second"
        assert (await b.get_auth_header(force_refresh_token=True))[
            "authorization"
        ] == "Bearer second"
    grants = [
        parse_qs(c.request.content.decode())["grant_type"][0] for c in route.calls
    ]
    assert grants == ["client_credentials", "refresh_token"]


@pytest.mark.asyncio
async def test_refresh_lifetime_is_carried_when_the_idp_omits_refresh_expires_in(
    client_settings, auth_token_response, monkeypatch
):
    """A rotating IdP that omits refresh_expires_in must not shave the buffer off
    the refresh lifetime on every refresh (15 s per cycle compounds)."""
    from datetime import timedelta
    from gundi_client_v2 import token_cache as tc

    base = tc._now()
    clock = {"now": base}
    monkeypatch.setattr(tc, "_now", lambda: clock["now"])
    rotated = {
        k: v for k, v in auth_token_response.items() if k != "refresh_expires_in"
    }

    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(200, json=auth_token_response)
        client = GundiClient(**client_settings)
        await client.get_auth_header()
        original = client.cached_token_refresh_expires_at
        route.respond(200, json={**rotated, "refresh_token": "rotated-refresh"})
        for _ in range(5):
            clock["now"] += timedelta(seconds=auth_token_response["expires_in"] + 60)
            await client.get_auth_header()
    assert client.cached_token_refresh_expires_at == original


@pytest.mark.asyncio
async def test_a_failed_refresh_marks_the_refresh_token_dead(
    client_settings, auth_token_response, monkeypatch
):
    """When the refresh grant is rejected and the full authentication also fails,
    the next call must not retry the dead refresh token first (2N requests
    during an outage); it goes straight to full authentication."""
    from datetime import timedelta
    from urllib.parse import parse_qs
    from gundi_client_v2 import token_cache as tc
    from gundi_client_v2.errors import AuthenticationError

    base = tc._now()
    clock = {"now": base}
    monkeypatch.setattr(tc, "_now", lambda: clock["now"])

    calls = []

    def respond(request):
        calls.append(parse_qs(request.content.decode())["grant_type"][0])
        if (
            len(calls) == 1
        ):  # the initial authentication succeeds; the IdP then rejects everything
            return httpx.Response(200, json=auth_token_response)
        return httpx.Response(400, json={"error": "invalid_grant"})

    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).mock(side_effect=respond)
        client = GundiClient(**client_settings)
        await client.get_auth_header()
        clock["now"] += timedelta(seconds=auth_token_response["expires_in"] + 60)
        for _ in range(2):
            with pytest.raises(AuthenticationError):
                await client.get_auth_header()
    grants = [
        parse_qs(c.request.content.decode())["grant_type"][0] for c in route.calls
    ]
    assert grants == [
        "client_credentials",
        "refresh_token",
        "client_credentials",
        "client_credentials",
    ]


def _separate_process(client, backend):
    """Give `client` its own memory layer, as a second process would have."""
    client._token_store = TokenStore(backend, memory=MemoryTokenCache())
    return client


@pytest.mark.asyncio
async def test_force_refresh_adopts_a_replacement_made_in_another_process(
    client_settings, auth_token_response
):
    """Across processes the memory layer holds the rejected token; the forced
    path must look past it at the backend before deciding to evict."""
    from urllib.parse import parse_qs

    backend = RedisTokenCache(client=FakeAsyncRedis(decode_responses=True))
    responses = iter(["first", "second", "third"])

    def issue(request):
        return httpx.Response(
            200, json={**auth_token_response, "access_token": next(responses)}
        )

    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).mock(side_effect=issue)
        a = _separate_process(
            GundiClient(**client_settings, token_cache=backend), backend
        )
        b = _separate_process(
            GundiClient(**client_settings, token_cache=backend), backend
        )
        assert (await a.get_auth_header())["authorization"] == "Bearer first"
        assert (await b.get_auth_header())["authorization"] == "Bearer first"
        assert (await a.get_auth_header(force_refresh_token=True))[
            "authorization"
        ] == "Bearer second"
        assert (await b.get_auth_header(force_refresh_token=True))[
            "authorization"
        ] == "Bearer second"
    grants = [
        parse_qs(c.request.content.decode())["grant_type"][0] for c in route.calls
    ]
    assert grants == ["client_credentials", "refresh_token"]


@pytest.mark.asyncio
async def test_a_forced_refresh_that_fails_does_not_republish_the_rejected_token(
    client_settings, auth_token_response
):
    fake = FakeAsyncRedis(decode_responses=True)
    backend = RedisTokenCache(client=fake)
    from gundi_client_v2.errors import AuthenticationError

    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(200, json=auth_token_response)
        client = GundiClient(**client_settings, token_cache=backend)
        await client.get_auth_header()
        route.respond(503, json={"error": "temporarily_unavailable"})
        with pytest.raises(AuthenticationError):
            await client.get_auth_header(force_refresh_token=True)
        assert await fake.keys("gundi-client:token:*") == []
        assert client.cached_token is None
        route.respond(200, json={**auth_token_response, "access_token": "fresh"})
        assert (await client.get_auth_header())["authorization"] == "Bearer fresh"


@pytest.mark.asyncio
async def test_a_fresh_instance_forcing_a_refresh_goes_to_the_idp(
    client_settings, auth_token_response
):
    """`gundi auth login` builds a new client and forces a refresh to validate the
    typed credentials; adopting a shared token would skip that validation."""
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(200, json=auth_token_response)
        await GundiClient(**client_settings).get_auth_header()
        await GundiClient(**client_settings).get_auth_header(force_refresh_token=True)
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_a_5xx_on_the_refresh_grant_keeps_the_refresh_token(
    client_settings, auth_token_response, monkeypatch
):
    """Only a rejection (4xx) means the refresh token is dead; an IdP outage
    must not discard a still-valid refresh token from the instance or the store."""
    from datetime import timedelta
    from urllib.parse import parse_qs
    from gundi_client_v2 import token_cache as tc
    from gundi_client_v2.errors import AuthenticationError

    base = tc._now()
    clock = {"now": base}
    monkeypatch.setattr(tc, "_now", lambda: clock["now"])
    fake = FakeAsyncRedis(decode_responses=True)
    backend = RedisTokenCache(client=fake)
    calls = []

    def respond(request):
        calls.append(parse_qs(request.content.decode())["grant_type"][0])
        if len(calls) == 1:
            return httpx.Response(200, json=auth_token_response)
        return httpx.Response(503, json={"error": "temporarily_unavailable"})

    async with respx.mock as mock:
        mock.post(TOKEN_URL).mock(side_effect=respond)
        client = GundiClient(**client_settings, token_cache=backend)
        await client.get_auth_header()
        clock["now"] += timedelta(seconds=auth_token_response["expires_in"] + 60)
        for _ in range(2):
            with pytest.raises(AuthenticationError):
                await client.get_auth_header()
    assert calls == [
        "client_credentials",
        "refresh_token",
        "client_credentials",
        "refresh_token",
        "client_credentials",
    ]
    assert client.cached_token_refresh_expires_at > clock["now"]
    assert await fake.keys("gundi-client:token:*") != []


def test_authentication_error_carries_status_and_oauth_error_code(auth_token_response):
    import asyncio as _asyncio
    from gundi_client_v2 import auth
    from gundi_client_v2.errors import AuthenticationError

    async def go():
        async with respx.mock as mock:
            mock.post(TOKEN_URL).respond(
                400, json={"error": "invalid_grant", "error_description": "stale"}
            )
            async with httpx.AsyncClient() as session:
                with pytest.raises(AuthenticationError) as info:
                    await auth.get_access_token_client_credentials(
                        session, TOKEN_URL, "c", "s"
                    )
        return info.value

    exc = _asyncio.run(go())
    assert exc.status_code == 400
    assert exc.error == "invalid_grant"


class _DownBackend:
    async def get(self, key):
        raise ConnectionError()

    async def set(self, key, token):
        raise ConnectionError()

    async def delete(self, key):
        raise ConnectionError()


@pytest.mark.asyncio
async def test_force_refresh_with_the_backend_down_adopts_an_in_process_sibling(
    client_settings, auth_token_response
):
    """A backend outage is a miss for reading other processes, not a reason to
    forget what a sibling in this process has already written."""
    from urllib.parse import parse_qs

    down = _DownBackend()
    responses = iter(["first", "second", "third"])

    def issue(request):
        return httpx.Response(
            200, json={**auth_token_response, "access_token": next(responses)}
        )

    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).mock(side_effect=issue)
        a = GundiClient(**client_settings, token_cache=down)
        b = GundiClient(**client_settings, token_cache=down)
        await a.get_auth_header()
        await b.get_auth_header()
        assert (await a.get_auth_header(force_refresh_token=True))[
            "authorization"
        ] == "Bearer second"
        assert (await b.get_auth_header(force_refresh_token=True))[
            "authorization"
        ] == "Bearer second"
    grants = [
        parse_qs(c.request.content.decode())["grant_type"][0] for c in route.calls
    ]
    assert grants == ["client_credentials", "refresh_token"]


@pytest.mark.asyncio
async def test_a_rejected_refresh_token_is_removed_from_the_backend(
    client_settings, auth_token_response, monkeypatch
):
    from datetime import timedelta
    from urllib.parse import parse_qs
    from gundi_client_v2 import token_cache as tc
    from gundi_client_v2.errors import AuthenticationError

    base = tc._now()
    clock = {"now": base}
    monkeypatch.setattr(tc, "_now", lambda: clock["now"])
    fake = FakeAsyncRedis(decode_responses=True)
    backend = RedisTokenCache(client=fake)
    calls = []

    def respond(request):
        calls.append(parse_qs(request.content.decode())["grant_type"][0])
        if len(calls) == 1:
            return httpx.Response(200, json=auth_token_response)
        return httpx.Response(400, json={"error": "invalid_grant"})

    async with respx.mock as mock:
        mock.post(TOKEN_URL).mock(side_effect=respond)
        client = _separate_process(
            GundiClient(**client_settings, token_cache=backend), backend
        )
        await client.get_auth_header()
        clock["now"] += timedelta(seconds=auth_token_response["expires_in"] + 60)
        with pytest.raises(AuthenticationError):
            await client.get_auth_header()
        assert await fake.keys("gundi-client:token:*") == []
        sibling = _separate_process(
            GundiClient(**client_settings, token_cache=backend), backend
        )
        with pytest.raises(AuthenticationError):
            await sibling.get_auth_header()
    assert calls == [
        "client_credentials",
        "refresh_token",
        "client_credentials",
        "client_credentials",
    ]


@pytest.mark.asyncio
async def test_a_429_on_the_refresh_grant_keeps_the_refresh_token(
    client_settings, auth_token_response, monkeypatch
):
    """Rate limiting is not a verdict on the refresh token."""
    from datetime import timedelta
    from urllib.parse import parse_qs
    from gundi_client_v2 import token_cache as tc
    from gundi_client_v2.errors import AuthenticationError

    base = tc._now()
    clock = {"now": base}
    monkeypatch.setattr(tc, "_now", lambda: clock["now"])
    fake = FakeAsyncRedis(decode_responses=True)
    backend = RedisTokenCache(client=fake)
    calls = []

    def respond(request):
        calls.append(parse_qs(request.content.decode())["grant_type"][0])
        if len(calls) == 1:
            return httpx.Response(200, json=auth_token_response)
        return httpx.Response(429, json={"error": "slow_down"})

    async with respx.mock as mock:
        mock.post(TOKEN_URL).mock(side_effect=respond)
        client = GundiClient(**client_settings, token_cache=backend)
        await client.get_auth_header()
        clock["now"] += timedelta(seconds=auth_token_response["expires_in"] + 60)
        with pytest.raises(AuthenticationError):
            await client.get_auth_header()
    assert client.cached_token_refresh_expires_at > clock["now"]
    assert await fake.keys("gundi-client:token:*") != []


@pytest.mark.asyncio
async def test_a_transport_error_during_a_forced_refresh_clears_the_instance_token(
    client_settings, auth_token_response
):
    from gundi_client_v2.errors import AuthenticationError

    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(
            200, json={**auth_token_response, "access_token": "rejected"}
        )
        client = GundiClient(**client_settings)
        await client.get_auth_header()
        route.mock(side_effect=httpx.ConnectError("boom"))
        with pytest.raises(AuthenticationError):
            await client.get_auth_header(force_refresh_token=True)
        assert client.cached_token is None
        route.mock(
            return_value=httpx.Response(
                200, json={**auth_token_response, "access_token": "fresh"}
            )
        )
        assert (await client.get_auth_header())["authorization"] == "Bearer fresh"


def test_authentication_error_declares_refresh_token_rejected():
    from gundi_client_v2.errors import AuthenticationError

    assert AuthenticationError("x").refresh_token_rejected is False
    assert (
        AuthenticationError("x", refresh_token_rejected=True).refresh_token_rejected
        is True
    )


@pytest.mark.asyncio
async def test_a_403_invalid_grant_on_the_refresh_grant_marks_the_refresh_token_dead(
    client_settings, auth_token_response, monkeypatch
):
    """Auth0 answers a revoked refresh token with 403 invalid_grant; the error
    code, not the status, is the verdict."""
    from datetime import timedelta
    from urllib.parse import parse_qs
    from gundi_client_v2 import token_cache as tc
    from gundi_client_v2.errors import AuthenticationError

    base = tc._now()
    clock = {"now": base}
    monkeypatch.setattr(tc, "_now", lambda: clock["now"])
    calls = []

    def respond(request):
        calls.append(parse_qs(request.content.decode())["grant_type"][0])
        if len(calls) == 1:
            return httpx.Response(200, json=auth_token_response)
        if calls[-1] == "refresh_token":
            return httpx.Response(403, json={"error": "invalid_grant"})
        return httpx.Response(503, json={"error": "temporarily_unavailable"})

    async with respx.mock as mock:
        mock.post(TOKEN_URL).mock(side_effect=respond)
        client = GundiClient(**client_settings)
        await client.get_auth_header()
        clock["now"] += timedelta(seconds=auth_token_response["expires_in"] + 60)
        for _ in range(2):
            with pytest.raises(AuthenticationError):
                await client.get_auth_header()
    assert calls == [
        "client_credentials",
        "refresh_token",
        "client_credentials",
        "client_credentials",
    ]


@pytest.mark.asyncio
async def test_a_transport_error_on_the_refresh_grant_does_not_retry_with_full_authentication(
    client_settings, auth_token_response, monkeypatch
):
    """A network that just failed will fail again; one attempt, one timeout, and
    the credentials are not sent down a broken connection."""
    from datetime import timedelta
    from gundi_client_v2 import token_cache as tc
    from gundi_client_v2.errors import AuthenticationError

    base = tc._now()
    clock = {"now": base}
    monkeypatch.setattr(tc, "_now", lambda: clock["now"])
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(200, json=auth_token_response)
        client = GundiClient(**client_settings)
        await client.get_auth_header()
        clock["now"] += timedelta(seconds=auth_token_response["expires_in"] + 60)
        route.mock(side_effect=httpx.ConnectError("down"))
        with pytest.raises(AuthenticationError) as info:
            await client.get_auth_header()
    assert route.call_count == 2  # the login, then exactly one refresh attempt
    assert info.value.status_code is None
    assert (
        client.cached_token_refresh_expires_at > clock["now"]
    )  # the refresh token is kept


def _expired(clock, auth_token_response):
    from datetime import timedelta

    clock["now"] += timedelta(seconds=auth_token_response["expires_in"] + 60)


@pytest.fixture
def refresh_scenario(client_settings, auth_token_response, monkeypatch):
    """A client holding a live refresh token whose access token has expired,
    plus a hook to script how the IdP answers the next grants."""
    from urllib.parse import parse_qs
    from gundi_client_v2 import token_cache as tc

    clock = {"now": tc._now()}
    monkeypatch.setattr(tc, "_now", lambda: clock["now"])
    calls = []
    script = {}

    def respond(request):
        grant = parse_qs(request.content.decode())["grant_type"][0]
        calls.append(grant)
        if len(calls) == 1:
            return httpx.Response(200, json=auth_token_response)
        answer = script.get(grant) or script["*"]
        return answer() if callable(answer) else answer

    async def run(expect_error=True):
        from gundi_client_v2.errors import AuthenticationError

        async with respx.mock as mock:
            mock.post(TOKEN_URL).mock(side_effect=respond)
            client = GundiClient(**client_settings)
            await client.get_auth_header()
            _expired(clock, auth_token_response)
            if expect_error:
                with pytest.raises(AuthenticationError) as info:
                    await client.get_auth_header()
                return client, calls, info.value
            await client.get_auth_header()
            return client, calls, None

    return script, run, clock


@pytest.mark.asyncio
async def test_a_401_invalid_client_on_the_refresh_grant_keeps_the_refresh_token(
    refresh_scenario,
):
    script, run, clock = refresh_scenario
    script["*"] = httpx.Response(401, json={"error": "invalid_client"})
    client, calls, exc = await run()
    assert calls == ["client_credentials", "refresh_token", "client_credentials"]
    assert exc.refresh_token_rejected is False
    assert client.cached_token_refresh_expires_at > clock["now"]


@pytest.mark.asyncio
async def test_a_5xx_body_that_says_invalid_grant_is_not_a_verdict(refresh_scenario):
    """A gateway that rewrites the status but forwards a body is not the IdP
    rejecting the refresh token; only 400 or 403 carry that verdict."""
    script, run, clock = refresh_scenario
    script["*"] = httpx.Response(502, json={"error": "invalid_grant"})
    client, calls, exc = await run()
    assert exc.refresh_token_rejected is False
    assert client.cached_token_refresh_expires_at > clock["now"]


@pytest.mark.asyncio
async def test_a_non_json_5xx_on_the_refresh_grant_still_falls_back_to_full_authentication(
    refresh_scenario, auth_token_response
):
    script, run, clock = refresh_scenario
    script["refresh_token"] = httpx.Response(503, text="<html>gateway timeout</html>")
    script["client_credentials"] = httpx.Response(
        200, json={**auth_token_response, "access_token": "recovered"}
    )
    client, calls, _ = await run(expect_error=False)
    assert calls == ["client_credentials", "refresh_token", "client_credentials"]
    assert client.cached_token.access_token == "recovered"


@pytest.mark.asyncio
async def test_a_malformed_2xx_refresh_body_falls_back_to_full_authentication(
    refresh_scenario, auth_token_response
):
    """Only a transport failure skips the full grant; a broken 200 body is a
    response and the full grant may well succeed."""
    script, run, clock = refresh_scenario
    script["refresh_token"] = httpx.Response(200, text="<html>captive portal</html>")
    script["client_credentials"] = httpx.Response(
        200, json={**auth_token_response, "access_token": "recovered"}
    )
    client, calls, _ = await run(expect_error=False)
    assert calls == ["client_credentials", "refresh_token", "client_credentials"]


@pytest.mark.asyncio
async def test_a_transport_error_is_flagged_on_the_exception(refresh_scenario):
    script, run, clock = refresh_scenario
    script["*"] = lambda: (_ for _ in ()).throw(httpx.ConnectError("down"))
    client, calls, exc = await run()
    assert exc.transport is True
    assert exc.status_code is None
    assert calls == ["client_credentials", "refresh_token"]


def test_a_malformed_client_credentials_token_body_is_an_authentication_error():
    import asyncio as _asyncio
    from gundi_client_v2 import auth
    from gundi_client_v2.errors import AuthenticationError

    async def go():
        async with respx.mock as mock:
            mock.post(TOKEN_URL).respond(200, json={"access_token": "x"})
            async with httpx.AsyncClient() as session:
                with pytest.raises(AuthenticationError) as info:
                    await auth.get_access_token_client_credentials(
                        session, TOKEN_URL, "c", "s"
                    )
        return info.value

    exc = _asyncio.run(go())
    assert exc.transport is False and exc.status_code is None
