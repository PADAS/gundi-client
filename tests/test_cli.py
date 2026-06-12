import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from gundi_client_v2.cli import app

runner = CliRunner()

BASE_URL = "https://api.fakeportal.com"
ISSUER = "https://fakeauth.com/auth/realms/dev"
TOKEN_URL = f"{ISSUER}/protocol/openid-connect/token"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
INTEGRATIONS_URL = f"{BASE_URL}/v2/integrations/"


def _clear_auth_env(monkeypatch):
    """Drop every auth env var so each fixture starts from a known-empty state.

    Without this, a developer's real .env (loaded by the client at import) could
    leak username/password/issuer into a test and change the selected grant.
    """
    for var in (
        "OAUTH_CLIENT_SECRET",
        "OAUTH_TOKEN_URL",
        "OAUTH_ISSUER",
        "OAUTH_AUDIENCE",
        "GUNDI_USERNAME",
        "GUNDI_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def cli_env(monkeypatch):
    """Client-credentials + explicit token URL."""
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GUNDI_API_BASE_URL", BASE_URL)
    monkeypatch.setenv("OAUTH_CLIENT_ID", "confidential-client")
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OAUTH_TOKEN_URL", TOKEN_URL)


@pytest.fixture
def cli_env_issuer(monkeypatch):
    """Client-credentials + OIDC discovery (OAUTH_ISSUER, no explicit token URL)."""
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GUNDI_API_BASE_URL", BASE_URL)
    monkeypatch.setenv("OAUTH_CLIENT_ID", "confidential-client")
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OAUTH_ISSUER", ISSUER)


@pytest.fixture
def cli_env_password(monkeypatch):
    """Password grant (public client): client id + username/password, NO secret."""
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GUNDI_API_BASE_URL", BASE_URL)
    monkeypatch.setenv("OAUTH_CLIENT_ID", "public-client")
    monkeypatch.setenv("GUNDI_USERNAME", "dev@example.com")
    monkeypatch.setenv("GUNDI_PASSWORD", "hunter2")
    monkeypatch.setenv("OAUTH_ISSUER", ISSUER)


def _mock_auth(mock, auth_token_response):
    mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)


def test_list_renders_table(
    cli_env, auth_token_response, destination_integration_details
):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 0, result.output
    # Header + the integration's id/name/type/enabled all present in the table.
    assert "ID" in result.output and "ENABLED" in result.output
    assert destination_integration_details["id"] in result.output
    assert "ER Load Testing" in result.output
    assert "earth_ranger" in result.output
    assert "true" in result.output


def test_list_with_issuer_uses_discovery(
    cli_env_issuer, auth_token_response, destination_integration_details
):
    # With only OAUTH_ISSUER set, the client must resolve the token endpoint
    # via the OIDC discovery document rather than a configured OAUTH_TOKEN_URL.
    with respx.mock(assert_all_called=False) as mock:
        discovery = mock.get(DISCOVERY_URL).respond(
            status_code=httpx.codes.OK,
            json={"issuer": ISSUER, "token_endpoint": TOKEN_URL},
        )
        _mock_auth(mock, auth_token_response)
        mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 0, result.output
    assert discovery.called
    assert destination_integration_details["id"] in result.output


def test_list_password_grant_without_secret(
    cli_env_password, auth_token_response, destination_integration_details
):
    # Password grant (public client): client_id + username/password, no secret.
    # build_client() must not require OAUTH_CLIENT_SECRET here.
    with respx.mock(assert_all_called=False) as mock:
        mock.get(DISCOVERY_URL).respond(
            status_code=httpx.codes.OK,
            json={"issuer": ISSUER, "token_endpoint": TOKEN_URL},
        )
        token_route = mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 0, result.output
    assert destination_integration_details["id"] in result.output
    # Confirm the password grant was used (not client_credentials).
    body = token_route.calls.last.request.content.decode()
    assert "grant_type=password" in body


def test_list_json_emits_parseable_json(
    cli_env, auth_token_response, destination_integration_details
):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list", "--json"])

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert parsed[0]["id"] == destination_integration_details["id"]


def test_list_forwards_type_filter(
    cli_env, auth_token_response, destination_integration_details
):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list", "--type", "earth_ranger"])

    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.params["type"] == "earth_ranger"


def test_list_follows_pagination(
    cli_env,
    auth_token_response,
    destination_integration_details,
    webhook_integration_details,
):
    next_url = f"{INTEGRATIONS_URL}?cursor=page2"
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(next_url).respond(
            status_code=httpx.codes.OK,
            json={"results": [webhook_integration_details], "next": None},
        )
        mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": next_url},
        )

        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 0, result.output
    assert destination_integration_details["id"] in result.output
    assert webhook_integration_details["id"] in result.output


def test_enable_patches_enabled_true(
    cli_env, auth_token_response, destination_integration_details
):
    integration_id = destination_integration_details["id"]
    url = f"{BASE_URL}/v2/integrations/{integration_id}/"
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        patch_route = mock.patch(url).respond(
            status_code=httpx.codes.OK, json={"id": integration_id, "enabled": True}
        )
        mock.get(url).respond(
            status_code=httpx.codes.OK, json=destination_integration_details
        )

        result = runner.invoke(app, ["integrations", "enable", integration_id])

    assert result.exit_code == 0, result.output
    sent = json.loads(patch_route.calls.last.request.content.decode())
    assert sent == {"enabled": True}
    assert "enabled" in result.output


def test_disable_patches_enabled_false(
    cli_env, auth_token_response, destination_integration_details
):
    integration_id = destination_integration_details["id"]
    disabled = {**destination_integration_details, "enabled": False}
    url = f"{BASE_URL}/v2/integrations/{integration_id}/"
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        patch_route = mock.patch(url).respond(
            status_code=httpx.codes.OK, json={"id": integration_id, "enabled": False}
        )
        mock.get(url).respond(status_code=httpx.codes.OK, json=disabled)

        result = runner.invoke(app, ["integrations", "disable", integration_id])

    assert result.exit_code == 0, result.output
    sent = json.loads(patch_route.calls.last.request.content.decode())
    assert sent == {"enabled": False}
    assert "disabled" in result.output


def test_missing_env_var_exits_2(monkeypatch):
    # No auth env vars set at all.
    for var in (
        "GUNDI_API_BASE_URL",
        "OAUTH_CLIENT_ID",
        "OAUTH_CLIENT_SECRET",
        "OAUTH_TOKEN_URL",
        "OAUTH_ISSUER",
    ):
        monkeypatch.delenv(var, raising=False)

    result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 2, result.output
    assert "GUNDI_API_BASE_URL" in result.output
    # The token-endpoint requirement names the discovery-friendly option first.
    assert "OAUTH_ISSUER" in result.output


def test_missing_token_endpoint_exits_2(monkeypatch):
    # Base creds present, but neither OAUTH_ISSUER nor OAUTH_TOKEN_URL is set.
    monkeypatch.setenv("GUNDI_API_BASE_URL", BASE_URL)
    monkeypatch.setenv("OAUTH_CLIENT_ID", "confidential-client")
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "shhh")
    monkeypatch.delenv("OAUTH_TOKEN_URL", raising=False)
    monkeypatch.delenv("OAUTH_ISSUER", raising=False)

    result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 2, result.output
    assert "OAUTH_ISSUER" in result.output
    assert "GUNDI_API_BASE_URL" not in result.output  # base creds were fine


def test_missing_credentials_exits_2(monkeypatch):
    # client_id + token endpoint present, but no secret AND no username/password.
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GUNDI_API_BASE_URL", BASE_URL)
    monkeypatch.setenv("OAUTH_CLIENT_ID", "some-client")
    monkeypatch.setenv("OAUTH_ISSUER", ISSUER)

    result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 2, result.output
    # The message points at both credential options.
    assert "OAUTH_CLIENT_SECRET" in result.output
    assert "GUNDI_USERNAME" in result.output


def test_api_error_exits_1_without_traceback(cli_env, auth_token_response):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.INTERNAL_SERVER_ERROR, json={"detail": "boom"}
        )

        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 1, result.output
    assert "Error:" in result.output
    assert "Traceback" not in result.output
