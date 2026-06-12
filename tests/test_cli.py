import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from gundi_client_v2.cli import app
from gundi_client_v2.cli import config_store, token_store

runner = CliRunner()

BASE_URL = "https://api.fakeportal.com"
ISSUER = "https://fakeauth.com/auth/realms/dev"
TOKEN_URL = f"{ISSUER}/protocol/openid-connect/token"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
INTEGRATIONS_URL = f"{BASE_URL}/v2/integrations/"


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Point XDG_CONFIG_HOME at a clean tmp dir for every test.

    Without this, raw-env tests (which don't configure a profile) would pick up
    a developer's real ~/.config/gundi/config.json and resolve its active
    environment instead of the env vars under test. Profile-based tests below
    set XDG_CONFIG_HOME to the same tmp_path and add their own environments.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)


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


def test_list_filters_by_type_client_side(
    cli_env,
    auth_token_response,
    destination_integration_details,
    webhook_integration_details,
):
    # The API filters `type` by UUID, not slug, so --type is applied client-side
    # on integration.type.value and is NOT forwarded as a query param.
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={
                "results": [
                    destination_integration_details,
                    webhook_integration_details,
                ],
                "next": None,
            },
        )

        result = runner.invoke(app, ["integrations", "list", "--type", "earth_ranger"])

    assert result.exit_code == 0, result.output
    # earth_ranger kept, the other type filtered out
    assert destination_integration_details["id"] in result.output
    assert webhook_integration_details["id"] not in result.output
    # slug is not sent to the server (it would 400 as "not a valid UUID")
    assert "type" not in route.calls.last.request.url.params


def test_list_type_filter_is_case_insensitive(
    cli_env, auth_token_response, destination_integration_details
):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list", "--type", "Earth_Ranger"])

    assert result.exit_code == 0, result.output
    assert destination_integration_details["id"] in result.output


def test_list_json_with_type_filter(
    cli_env,
    auth_token_response,
    destination_integration_details,
    webhook_integration_details,
):
    # --type also narrows JSON output.
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={
                "results": [
                    destination_integration_details,
                    webhook_integration_details,
                ],
                "next": None,
            },
        )

        result = runner.invoke(
            app, ["integrations", "list", "--type", "earth_ranger", "--json"]
        )

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert [i["id"] for i in parsed] == [destination_integration_details["id"]]


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


def test_resolve_environment_precedence(tmp_path, monkeypatch):
    from gundi_client_v2.cli import _client

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config_store.add_environment("dev", {"base_url": "u", "client_id": "c"})
    config_store.add_environment("prod", {"base_url": "u", "client_id": "c"})
    config_store.set_active("prod")

    # stored active wins when nothing else given
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    assert _client.resolve_environment(None) == "prod"
    # GUNDI_PROFILE beats active
    monkeypatch.setenv("GUNDI_PROFILE", "dev")
    assert _client.resolve_environment(None) == "dev"
    # explicit flag beats env var
    assert _client.resolve_environment("prod") == "prod"


def test_resolve_environment_none_without_config(tmp_path, monkeypatch):
    from gundi_client_v2.cli import _client

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    assert _client.resolve_environment(None) is None


def test_resolve_environment_unknown_raises(tmp_path, monkeypatch):
    from gundi_client_v2.cli import _client

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(config_store.ConfigError):
        _client.resolve_environment("ghost")


def test_list_uses_cached_token_no_token_post(
    tmp_path, monkeypatch, destination_integration_details
):
    # A valid cached token must be reused: NO token POST should occur.
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    config_store.add_environment(
        "prod", {"base_url": BASE_URL, "client_id": "c", "token_url": TOKEN_URL}
    )
    config_store.set_active("prod")

    class _Tok:
        access_token = "CACHED"
        refresh_token = "R"
        token_type = "Bearer"

    future = datetime.now(timezone.utc) + timedelta(hours=1)
    token_store.save_token("prod", _Tok(), future, future)

    with respx.mock(assert_all_called=False) as mock:
        # NOTE: deliberately do NOT mock the token endpoint.
        integrations_route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )
        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 0, result.output
    assert destination_integration_details["id"] in result.output
    assert integrations_route.called
    # The Authorization header carried the cached token.
    assert (
        integrations_route.calls.last.request.headers["authorization"]
        == "Bearer CACHED"
    )


def test_list_profile_flag_overrides_active(
    tmp_path, monkeypatch, destination_integration_details
):
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    config_store.add_environment(
        "prod", {"base_url": BASE_URL, "client_id": "c", "token_url": TOKEN_URL}
    )
    config_store.add_environment(
        "dev", {"base_url": BASE_URL, "client_id": "c", "token_url": TOKEN_URL}
    )
    config_store.set_active("prod")

    class _Tok:
        access_token = "DEVTOK"
        refresh_token = "R"
        token_type = "Bearer"

    future = datetime.now(timezone.utc) + timedelta(hours=1)
    token_store.save_token("dev", _Tok(), future, future)

    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )
        result = runner.invoke(app, ["integrations", "list", "--profile", "dev"])

    assert result.exit_code == 0, result.output
    assert route.calls.last.request.headers["authorization"] == "Bearer DEVTOK"


def test_list_unknown_profile_exits_2(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    result = runner.invoke(app, ["integrations", "list", "--profile", "ghost"])
    assert result.exit_code == 2, result.output
    assert "unknown environment" in result.output
