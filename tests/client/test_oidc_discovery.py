import httpx
import pytest
import respx
from urllib.parse import parse_qs

from gundi_client_v2 import auth, errors
from gundi_client_v2.client import GundiClient


@pytest.mark.asyncio
async def test_discover_token_endpoint_success():
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    expected = "https://idp.example.com/realms/dev/protocol/openid-connect/token"
    async with respx.mock as mock:
        mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer, "token_endpoint": expected},
        )
        async with httpx.AsyncClient() as session:
            result = await auth.discover_token_endpoint(session, issuer)
        assert result == expected


@pytest.mark.asyncio
async def test_discover_token_endpoint_uses_cache_on_second_call():
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    expected = "https://idp.example.com/realms/dev/protocol/openid-connect/token"
    async with respx.mock as mock:
        route = mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer, "token_endpoint": expected},
        )
        async with httpx.AsyncClient() as session:
            first = await auth.discover_token_endpoint(session, issuer)
            second = await auth.discover_token_endpoint(session, issuer)
        assert first == second == expected
        assert route.call_count == 1  # second call must NOT hit the network


@pytest.mark.asyncio
async def test_discover_token_endpoint_trailing_slash_shares_cache_entry():
    issuer_plain = "https://idp.example.com/realms/dev"
    issuer_slash = "https://idp.example.com/realms/dev/"
    discovery_url = f"{issuer_plain}/.well-known/openid-configuration"
    expected = "https://idp.example.com/realms/dev/protocol/openid-connect/token"
    async with respx.mock as mock:
        route = mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer_plain, "token_endpoint": expected},
        )
        async with httpx.AsyncClient() as session:
            a = await auth.discover_token_endpoint(session, issuer_plain)
            b = await auth.discover_token_endpoint(session, issuer_slash)
        assert a == b == expected
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_discover_token_endpoint_5xx_raises_authentication_error():
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    async with respx.mock as mock:
        mock.get(discovery_url).respond(status_code=503, text="Service Unavailable")
        async with httpx.AsyncClient() as session:
            with pytest.raises(errors.AuthenticationError) as exc:
                await auth.discover_token_endpoint(session, issuer)
        assert "OIDC discovery failed" in str(exc.value)
        assert issuer in str(exc.value)


@pytest.mark.asyncio
async def test_discover_token_endpoint_missing_token_endpoint_raises():
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    async with respx.mock as mock:
        mock.get(discovery_url).respond(
            status_code=httpx.codes.OK, json={"issuer": issuer}  # no token_endpoint
        )
        async with httpx.AsyncClient() as session:
            with pytest.raises(errors.AuthenticationError) as exc:
                await auth.discover_token_endpoint(session, issuer)
        assert "missing 'token_endpoint'" in str(exc.value)


@pytest.mark.asyncio
async def test_clear_discovery_cache_invalidates_cached_entry():
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    expected = "https://idp.example.com/realms/dev/protocol/openid-connect/token"
    async with respx.mock as mock:
        route = mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer, "token_endpoint": expected},
        )
        async with httpx.AsyncClient() as session:
            await auth.discover_token_endpoint(session, issuer)
            auth.clear_discovery_cache()
            await auth.discover_token_endpoint(session, issuer)
        assert route.call_count == 2  # cache was cleared → second call re-fetches


@pytest.mark.asyncio
async def test_discover_token_endpoint_non_string_value_raises():
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    async with respx.mock as mock:
        mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer, "token_endpoint": None},
        )
        async with httpx.AsyncClient() as session:
            with pytest.raises(errors.AuthenticationError) as exc:
                await auth.discover_token_endpoint(session, issuer)
        assert "non-string 'token_endpoint'" in str(exc.value)


@pytest.mark.asyncio
async def test_explicit_oauth_token_url_skips_discovery(auth_token_response):
    explicit = "https://idp.example.com/explicit/token"
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    client = GundiClient(
        oauth_token_url=explicit,
        oauth_issuer=issuer,
        oauth_client_id="public-client",
        username="alice",
        password="s3cret",
        base_url="https://api.fakeportal.com",
    )
    async with respx.mock as mock:
        discovery_route = mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer, "token_endpoint": "https://wrong.example/token"},
        )
        token_route = mock.post(explicit).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        await client.get_access_token()
        assert discovery_route.call_count == 0  # explicit URL wins
        assert token_route.call_count == 1
        body = parse_qs(token_route.calls.last.request.content.decode())
        assert body["grant_type"] == ["password"]


@pytest.mark.asyncio
async def test_oauth_issuer_only_triggers_discovery(auth_token_response):
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    discovered_token_url = "https://idp.example.com/realms/dev/protocol/openid-connect/token"
    # Pass oauth_token_url=None explicitly so any OAUTH_TOKEN_URL env var
    # cannot leak through settings.OAUTH_TOKEN_URL.
    client = GundiClient(
        oauth_token_url=None,
        oauth_issuer=issuer,
        oauth_client_id="public-client",
        username="alice",
        password="s3cret",
        base_url="https://api.fakeportal.com",
    )
    async with respx.mock as mock:
        discovery_route = mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer, "token_endpoint": discovered_token_url},
        )
        token_route = mock.post(discovered_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        await client.get_access_token()
        assert discovery_route.call_count == 1
        assert token_route.call_count == 1


@pytest.mark.asyncio
async def test_no_token_url_or_issuer_raises():
    client = GundiClient(
        oauth_client_id="public-client",
        username="alice",
        password="s3cret",
        base_url="https://api.fakeportal.com",
    )
    client.oauth_token_url = None
    client.oauth_issuer = None
    with pytest.raises(errors.AuthenticationError) as exc:
        await client.get_access_token()
    assert str(exc.value) == "No token URL configured. Set oauth_token_url or oauth_issuer."


@pytest.mark.asyncio
async def test_refresh_branch_uses_discovered_url_after_initial_auth(auth_token_response):
    """Regression: in the issuer-only flow, the refresh branch fires after the
    access token expires; it must reuse the URL discovered during the initial auth
    (served from auth._DISCOVERY_CACHE on the second call), not pass None."""
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    discovered_token_url = "https://idp.example.com/realms/dev/protocol/openid-connect/token"
    client = GundiClient(
        oauth_token_url=None,
        oauth_issuer=issuer,
        oauth_client_id="public-client",
        username="alice",
        password="s3cret",
        base_url="https://api.fakeportal.com",
    )
    async with respx.mock as mock:
        discovery_route = mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer, "token_endpoint": discovered_token_url},
        )
        token_route = mock.post(discovered_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        await client.get_access_token()                       # initial password grant via discovery
        await client.get_access_token(force_refresh_token=True)  # refresh branch fires
        # Discovery happened exactly once; both token requests went to the discovered URL.
        assert discovery_route.call_count == 1
        assert token_route.call_count == 2
        # Second call should have been the refresh grant — confirm via grant_type.
        second_body = parse_qs(token_route.calls[1].request.content.decode())
        assert second_body["grant_type"] == ["refresh_token"]


@pytest.mark.asyncio
async def test_clear_discovery_cache_forces_rediscovery_for_existing_client(auth_token_response):
    """After clear_discovery_cache(), a client that previously discovered must rediscover
    on its next auth attempt — i.e. the cache invalidation reaches the live client."""
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    discovered_token_url = "https://idp.example.com/realms/dev/protocol/openid-connect/token"
    client = GundiClient(
        oauth_token_url=None,
        oauth_issuer=issuer,
        oauth_client_id="public-client",
        username="alice",
        password="s3cret",
        base_url="https://api.fakeportal.com",
    )
    async with respx.mock as mock:
        discovery_route = mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer, "token_endpoint": discovered_token_url},
        )
        mock.post(discovered_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        await client.get_access_token()                       # initial auth via discovery
        assert discovery_route.call_count == 1
        auth.clear_discovery_cache()                          # operator invalidates
        await client.get_access_token(force_refresh_token=True)  # next auth on the SAME client
        assert discovery_route.call_count == 2                # must have re-discovered
