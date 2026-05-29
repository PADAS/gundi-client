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
        assert params["grant_type"] == ["urn:ietf:params:oauth:grant-type:uma-ticket"]
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
                headers={"location": "https://cdip-auth.pamdas.org/auth/realms/x/protocol/openid-connect/auth?response_type=code"},
            ),
            httpx.Response(status_code=httpx.codes.OK, json=integration_type_payload),
        ]
        result = await gundi_client_v2.register_integration_type(integration_type_payload)
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
                headers={"location": "https://cdip-auth.pamdas.org/auth/realms/x/protocol/openid-connect/auth?response_type=code"},
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
