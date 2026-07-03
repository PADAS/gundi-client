import httpx
import pytest
import respx
from urllib.parse import parse_qs

from gundi_client_v2.client import GundiClient
from gundi_core.schemas.v2 import IntegrationType


def _token_body(route):
    return parse_qs(route.calls.last.request.content.decode())


@pytest.mark.asyncio
async def test_authenticates_with_oauth_kwargs(auth_token_response):
    client = GundiClient(
        oauth_token_url="https://fakeauth.com/realms/dev/protocol/openid-connect/token",
        oauth_client_id="confidential-client",
        oauth_client_secret="shhh",
        oauth_audience="my-portal",
        base_url="https://api.fakeportal.com",
    )
    async with respx.mock as mock:
        token_route = mock.post(client.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        header = await client.get_auth_header()
        assert header["authorization"].startswith("Bearer ")
        params = _token_body(token_route)
        assert params["grant_type"] == ["client_credentials"]
        assert params["client_id"] == ["confidential-client"]
        assert params["client_secret"] == ["shhh"]


@pytest.mark.asyncio
async def test_post_retries_on_login_redirect(auth_token_response, gundi_client_v2):
    integration_type_payload = {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "name": "Test Integration",
        "value": "test_integration",
        "description": "A test integration type",
        "actions": [],
    }
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        type_url = f"{gundi_client_v2.integrations_endpoint}/types/"
        mock.post(type_url).side_effect = [
            httpx.Response(
                status_code=302,
                headers={
                    "location": "https://cdip-auth.pamdas.org/auth/realms/x/protocol/openid-connect/auth?response_type=code"
                },
            ),
            httpx.Response(status_code=httpx.codes.OK, json=integration_type_payload),
        ]
        result = await gundi_client_v2.register_integration_type(
            integration_type_payload
        )
        assert result == IntegrationType.parse_obj(integration_type_payload)


@pytest.mark.asyncio
async def test_get_retries_on_login_redirect_preserves_custom_headers(
    auth_token_response, gundi_client_v2
):
    # The _get 302-retry must merge the refreshed Authorization header with any
    # caller-supplied headers (regression guard for the headers={**auth_headers, **headers} fix).
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        target_url = f"{gundi_client_v2.connections_endpoint}/some-id/"
        route = mock.get(target_url)
        route.side_effect = [
            httpx.Response(
                status_code=302,
                headers={
                    "location": "https://cdip-auth.pamdas.org/auth/realms/x/protocol/openid-connect/auth?response_type=code"
                },
            ),
            httpx.Response(status_code=httpx.codes.OK, json={}),
        ]
        response = await gundi_client_v2._get(target_url, headers={"x-custom": "val"})
        assert response.status_code == 200
        assert route.call_count == 2
        retried = route.calls[1].request
        assert retried.headers.get("x-custom") == "val"
        assert "authorization" in retried.headers


def test_keycloak_settings_aliases_preserved():
    # The pre-rename module constants must remain importable as aliases of the OAUTH_* values.
    from gundi_client_v2 import settings

    assert settings.KEYCLOAK_ISSUER == settings.OAUTH_ISSUER
    assert settings.KEYCLOAK_CLIENT_ID == settings.OAUTH_CLIENT_ID
    assert settings.KEYCLOAK_CLIENT_SECRET == settings.OAUTH_CLIENT_SECRET
    assert settings.KEYCLOAK_AUDIENCE == settings.OAUTH_AUDIENCE


@pytest.mark.asyncio
async def test_keycloak_kwargs_backward_compatible():
    client = GundiClient(
        oauth_token_url="https://fakeauth.com/realms/dev/protocol/openid-connect/token",
        keycloak_client_id="legacy-client",
        keycloak_client_secret="legacy-secret",
        keycloak_audience="legacy-aud",
        base_url="https://api.fakeportal.com",
    )
    assert client.client_id == "legacy-client"
    assert client.client_secret == "legacy-secret"
    assert client.audience == "legacy-aud"


@pytest.mark.asyncio
async def test_token_request_non_json_2xx_raises_auth_error():
    from gundi_client_v2 import auth, errors

    url = "https://idp.example.com/token"
    async with respx.mock as mock:
        mock.post(url).respond(status_code=httpx.codes.OK, text="<html>not json</html>")
        async with httpx.AsyncClient() as session:
            with pytest.raises(errors.AuthenticationError):
                await auth._token_request(session, url, {"grant_type": "x"})


@pytest.mark.asyncio
async def test_token_request_missing_fields_2xx_raises_auth_error():
    from gundi_client_v2 import auth, errors

    url = "https://idp.example.com/token"
    async with respx.mock as mock:
        mock.post(url).respond(status_code=httpx.codes.OK, json={"not": "a token"})
        async with httpx.AsyncClient() as session:
            with pytest.raises(errors.AuthenticationError):
                await auth._token_request(session, url, {"grant_type": "x"})


@pytest.mark.asyncio
async def test_non_json_2xx_error_includes_url_and_status():
    from gundi_client_v2 import auth, errors

    url = "https://idp.example.com/token"
    async with respx.mock as mock:
        mock.post(url).respond(status_code=httpx.codes.OK, text="<html>nope</html>")
        async with httpx.AsyncClient() as session:
            with pytest.raises(errors.AuthenticationError) as exc:
                await auth._token_request(session, url, {"grant_type": "x"})
    msg = str(exc.value)
    assert url in msg and "200" in msg


@pytest.mark.asyncio
async def test_refresh_access_token_null_refresh_token_reuses_fallback():
    from gundi_client_v2 import auth
    from gundi_core.schemas import OAuthToken

    url = "https://idp.example.com/token"
    fallback = OAuthToken(
        access_token="old",
        refresh_token="RT_OLD",
        token_type="Bearer",
        expires_in=60,
        refresh_expires_in=3600,
    )
    async with respx.mock as mock:
        mock.post(url).respond(
            status_code=httpx.codes.OK,
            json={
                "access_token": "new",
                "token_type": "Bearer",
                "expires_in": 60,
                "refresh_token": None,  # IdP returned explicit null
            },
        )
        async with httpx.AsyncClient() as session:
            token, rotated = await auth.refresh_access_token(
                session=session,
                oauth_token_url=url,
                client_id="c",
                refresh_token="RT_OLD",
                fallback=fallback,
            )
    assert token.access_token == "new"
    assert token.refresh_token == "RT_OLD"  # reused fallback, not the null
    assert rotated is False


@pytest.mark.asyncio
async def test_post_token_non_dict_2xx_raises_auth_error():
    # A 2xx JSON non-object (e.g. []) must become a clean AuthenticationError
    # (with URL + status), not an AttributeError in callers doing body.get(...).
    from gundi_client_v2 import auth, errors
    from gundi_core.schemas import OAuthToken

    url = "https://idp.example.com/token"
    fallback = OAuthToken(
        access_token="old",
        refresh_token="RT",
        token_type="Bearer",
        expires_in=60,
        refresh_expires_in=3600,
    )
    async with respx.mock as mock:
        mock.post(url).respond(status_code=httpx.codes.OK, json=[])
        async with httpx.AsyncClient() as session:
            with pytest.raises(errors.AuthenticationError) as exc:
                await auth.refresh_access_token(
                    session=session,
                    oauth_token_url=url,
                    client_id="c",
                    refresh_token="RT",
                    fallback=fallback,
                )
    msg = str(exc.value)
    assert url in msg and "200" in msg


@pytest.mark.asyncio
async def test_validation_error_message_includes_url():
    from gundi_client_v2 import auth, errors

    url = "https://idp.example.com/token"
    async with respx.mock as mock:
        mock.post(url).respond(status_code=httpx.codes.OK, json={"not": "a token"})
        async with httpx.AsyncClient() as session:
            with pytest.raises(errors.AuthenticationError) as exc:
                await auth._token_request(session, url, {"grant_type": "x"})
    assert url in str(exc.value)
