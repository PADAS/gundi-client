import httpx
import pytest
import respx
from datetime import datetime, timezone
from urllib.parse import parse_qs

from gundi_client_v2 import auth, errors
from gundi_client_v2.client import GundiClient

TOKEN_URL = "https://fakeauth.com/realms/dev/protocol/openid-connect/token"


def _public_password_client(**overrides):
    kwargs = dict(
        oauth_token_url=TOKEN_URL,
        oauth_client_id="public-client",
        username="alice",
        password="s3cret",
        base_url="https://api.fakeportal.com",
    )
    kwargs.update(overrides)
    client = GundiClient(**kwargs)
    if "oauth_client_secret" not in overrides:
        client.client_secret = None
    return client


def _confidential_client(**overrides):
    kwargs = dict(
        oauth_token_url=TOKEN_URL,
        oauth_client_id="confidential-client",
        oauth_client_secret="shhh",
        base_url="https://api.fakeportal.com",
    )
    kwargs.update(overrides)
    client = GundiClient(**kwargs)
    client.username = None
    client.password = None
    return client


def _body(route, index=-1):
    return parse_qs(route.calls[index].request.content.decode())


@pytest.mark.asyncio
async def test_password_grant_payload(auth_token_response):
    client = _public_password_client()
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        await client.get_access_token()
        params = _body(route)
        assert params["grant_type"] == ["password"]
        assert params["username"] == ["alice"]
        assert params["password"] == ["s3cret"]
        assert params["scope"] == ["openid"]
        assert "client_secret" not in params


@pytest.mark.asyncio
async def test_audience_omitted_when_unset(auth_token_response):
    client = _confidential_client()
    client.audience = None
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        await client.get_access_token()
        assert "audience" not in _body(route)


@pytest.mark.asyncio
async def test_audience_included_when_set(auth_token_response):
    client = _confidential_client(oauth_audience="my-portal")
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        await client.get_access_token()
        assert _body(route)["audience"] == ["my-portal"]


@pytest.mark.asyncio
async def test_scope_override(auth_token_response):
    client = _confidential_client(oauth_scope="openid profile")
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        await client.get_access_token()
        assert _body(route)["scope"] == ["openid profile"]


@pytest.mark.asyncio
async def test_error_body_surfaced(auth_token_response):
    client = _confidential_client()
    async with respx.mock as mock:
        mock.post(TOKEN_URL).respond(
            status_code=401,
            json={"error": "invalid_client", "error_description": "Invalid client credentials"},
        )
        with pytest.raises(errors.AuthenticationError) as exc:
            await client.get_access_token()
        assert "invalid_client" in str(exc.value)
        assert "Invalid client credentials" in str(exc.value)


@pytest.mark.asyncio
async def test_refresh_grant_used_and_password_not_resent(auth_token_response):
    client = _public_password_client()
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        await client.get_access_token()
        await client.get_access_token(force_refresh_token=True)
        assert route.call_count == 2
        assert _body(route, 0)["grant_type"] == ["password"]
        second = _body(route, 1)
        assert second["grant_type"] == ["refresh_token"]
        assert "refresh_token" in second
        assert "password" not in second
        assert "client_secret" not in second


@pytest.mark.asyncio
async def test_refresh_failure_falls_back_to_full_auth(auth_token_response):
    client = _public_password_client()
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL)
        route.side_effect = [
            httpx.Response(httpx.codes.OK, json=auth_token_response),
            httpx.Response(400, json={"error": "invalid_grant", "error_description": "expired"}),
            httpx.Response(httpx.codes.OK, json=auth_token_response),
        ]
        await client.get_access_token()
        await client.get_access_token(force_refresh_token=True)
        assert route.call_count == 3
        assert _body(route, 1)["grant_type"] == ["refresh_token"]
        assert _body(route, 2)["grant_type"] == ["password"]


@pytest.mark.asyncio
async def test_no_credentials_raises():
    client = GundiClient(oauth_token_url=TOKEN_URL, base_url="https://api.fakeportal.com")
    client.client_id = None
    client.client_secret = None
    client.username = None
    client.password = None
    with pytest.raises(errors.AuthenticationError):
        await client.get_access_token()


@pytest.mark.asyncio
async def test_full_auth_when_token_and_refresh_expired(auth_token_response):
    client = _public_password_client()
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        await client.get_access_token()  # initial password grant, caches a refresh token
        # Simulate BOTH the access token and the refresh token having expired:
        client.cached_token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        client.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        await client.get_access_token()  # must skip refresh and do a full password grant
        assert route.call_count == 2
        assert _body(route, 1)["grant_type"] == ["password"]


@pytest.mark.asyncio
async def test_short_lived_token_not_immediately_expired(auth_token_response):
    short = dict(auth_token_response)
    short["expires_in"] = 10
    short["refresh_expires_in"] = 10
    client = _public_password_client()
    async with respx.mock as mock:
        mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=short)
        await client.get_access_token()
        # With the half-life clamp, a 10s token must NOT be treated as already expired.
        assert client.cached_token_expires_at > datetime.now(tz=timezone.utc)


@pytest.mark.asyncio
async def test_confidential_refresh_sends_client_secret(auth_token_response):
    # A confidential (uma-ticket) client MUST send its client_secret on the refresh grant.
    client = _confidential_client()
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        await client.get_access_token()                          # initial uma-ticket grant
        await client.get_access_token(force_refresh_token=True)  # refresh grant
        assert route.call_count == 2
        second = _body(route, 1)
        assert second["grant_type"] == ["refresh_token"]
        assert second["client_secret"] == ["shhh"]


@pytest.mark.asyncio
async def test_error_body_non_json_falls_back_to_status():
    # A non-JSON error body must still produce an AuthenticationError carrying the status code.
    client = _confidential_client()
    async with respx.mock as mock:
        mock.post(TOKEN_URL).respond(status_code=503, text="Service Unavailable")
        with pytest.raises(errors.AuthenticationError) as exc:
            await client.get_access_token()
        assert "503" in str(exc.value)


@pytest.mark.asyncio
async def test_error_body_non_object_json_falls_back_to_status():
    # Valid JSON but not an object (string/list/null) must NOT escape as AttributeError —
    # the helper must still produce an AuthenticationError carrying the status code so the
    # refresh-fallback path in _refresh_token continues to work.
    client = _confidential_client()
    async with respx.mock as mock:
        mock.post(TOKEN_URL).respond(status_code=400, json=["invalid_grant"])
        with pytest.raises(errors.AuthenticationError) as exc:
            await client.get_access_token()
        assert "400" in str(exc.value)


@pytest.mark.asyncio
async def test_refresh_preserves_cached_refresh_token_when_omitted(auth_token_response):
    # RFC 6749 §6: the new refresh_token is OPTIONAL on a refresh response. When the
    # IdP omits it, the cached refresh_token and its expiry must be preserved (and the
    # user's password must NOT be re-sent).
    client = _public_password_client()
    partial_refresh_response = {
        "access_token": "new-access-token-value",
        "expires_in": auth_token_response["expires_in"],
        "token_type": "Bearer",
    }
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL)
        route.side_effect = [
            httpx.Response(httpx.codes.OK, json=auth_token_response),       # initial password grant
            httpx.Response(httpx.codes.OK, json=partial_refresh_response),  # refresh: no refresh_token
        ]
        await client.get_access_token()
        original_refresh_token = client.cached_token.refresh_token
        original_refresh_expires_at = client.cached_token_refresh_expires_at

        await client.get_access_token(force_refresh_token=True)

        # The refresh grant fired exactly once — no silent fall-through to a second full auth.
        assert route.call_count == 2
        assert _body(route, 1)["grant_type"] == ["refresh_token"]
        # The user's password was NOT re-sent on the refresh.
        assert "password" not in _body(route, 1)
        # Access token rotated to the new value from the partial response.
        assert client.cached_token.access_token == "new-access-token-value"
        # Cached refresh token + its expiry are preserved across the partial refresh.
        assert client.cached_token.refresh_token == original_refresh_token
        assert client.cached_token_refresh_expires_at == original_refresh_expires_at


@pytest.mark.asyncio
async def test_password_grant_requires_client_id():
    # username/password without a client_id must fail locally with a clear configuration
    # error rather than firing a half-formed token request the IdP would reject.
    client = GundiClient(
        oauth_token_url=TOKEN_URL,
        base_url="https://api.fakeportal.com",
        username="alice",
        password="s3cret",
    )
    client.client_id = None
    client.client_secret = None
    with pytest.raises(errors.AuthenticationError) as exc:
        await client.get_access_token()
    assert "client_id" in str(exc.value)


@pytest.mark.asyncio
async def test_get_access_token_client_credentials_payload(auth_token_response):
    """RFC 6749 §4.4: client_credentials grant sends client_id+secret with grant_type=client_credentials."""
    token_url = "https://idp.example.com/oauth/token"
    async with respx.mock as mock:
        route = mock.post(token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        async with httpx.AsyncClient() as session:
            token = await auth.get_access_token_client_credentials(
                session,
                oauth_token_url=token_url,
                client_id="cid",
                client_secret="csecret",
            )
        params = parse_qs(route.calls.last.request.content.decode())
        assert params["grant_type"] == ["client_credentials"]
        assert params["client_id"] == ["cid"]
        assert params["client_secret"] == ["csecret"]
        assert params["scope"] == ["openid"]
        assert "audience" not in params
        assert token.access_token == auth_token_response["access_token"]


@pytest.mark.asyncio
async def test_get_access_token_client_credentials_with_audience_and_scope(auth_token_response):
    token_url = "https://idp.example.com/oauth/token"
    async with respx.mock as mock:
        route = mock.post(token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        async with httpx.AsyncClient() as session:
            token = await auth.get_access_token_client_credentials(
                session,
                oauth_token_url=token_url,
                client_id="cid",
                client_secret="csecret",
                audience="my-api",
                scope="openid api",
            )
        params = parse_qs(route.calls.last.request.content.decode())
        assert params["audience"] == ["my-api"]
        assert params["scope"] == ["openid api"]
        assert token.access_token == auth_token_response["access_token"]


@pytest.mark.asyncio
async def test_get_access_token_client_credentials_refreshless_response_parses():
    """RFC 6749 §4.4.3: client_credentials response SHOULD NOT include refresh_token.
    The function backfills empty refresh fields so OAuthToken (which requires them) still parses."""
    refreshless = {
        "access_token": "cc-token-value",
        "expires_in": 1800,
        "token_type": "Bearer",
        # NO refresh_token or refresh_expires_in
    }
    token_url = "https://idp.example.com/oauth/token"
    async with respx.mock as mock:
        mock.post(token_url).respond(status_code=httpx.codes.OK, json=refreshless)
        async with httpx.AsyncClient() as session:
            token = await auth.get_access_token_client_credentials(
                session,
                oauth_token_url=token_url,
                client_id="cid",
                client_secret="csecret",
            )
        assert token.access_token == "cc-token-value"
        assert token.refresh_token == ""
        assert token.refresh_expires_in == 0


@pytest.mark.asyncio
async def test_get_access_token_client_credentials_explicit_null_refresh_fields():
    """Some IdPs serialize 'no refresh token' as explicit null. The function must
    still produce a valid OAuthToken, treating null like missing."""
    null_refresh_response = {
        "access_token": "cc-token-value",
        "expires_in": 1800,
        "token_type": "Bearer",
        "refresh_token": None,
        "refresh_expires_in": None,
    }
    token_url = "https://idp.example.com/oauth/token"
    async with respx.mock as mock:
        mock.post(token_url).respond(status_code=httpx.codes.OK, json=null_refresh_response)
        async with httpx.AsyncClient() as session:
            token = await auth.get_access_token_client_credentials(
                session,
                oauth_token_url=token_url,
                client_id="cid",
                client_secret="csecret",
            )
        assert token.access_token == "cc-token-value"
        assert token.refresh_token == ""
        assert token.refresh_expires_in == 0
