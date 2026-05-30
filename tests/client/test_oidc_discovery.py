import httpx
import pytest
import respx

from gundi_client_v2 import auth, errors


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
