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
TYPES_URL = f"{BASE_URL}/v2/integrations/types/"
LOGS_URL = f"{BASE_URL}/v2/logs/"


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


def test_list_resolves_type_slug_to_uuid(
    cli_env, auth_token_response, destination_integration_details
):
    # --type <slug> is resolved to the type's UUID via the types endpoint, then
    # passed as the server-side `type` filter (the API rejects a raw slug).
    type_payload = destination_integration_details["type"]
    type_id = type_payload["id"]
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        types_route = mock.get(TYPES_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [type_payload], "next": None},
        )
        intg_route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list", "--type", "earth_ranger"])

    assert result.exit_code == 0, result.output
    assert types_route.called
    assert destination_integration_details["id"] in result.output
    assert intg_route.calls.last.request.url.params["type"] == type_id


def test_list_type_slug_is_case_insensitive(
    cli_env, auth_token_response, destination_integration_details
):
    type_payload = destination_integration_details["type"]
    type_id = type_payload["id"]
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(TYPES_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [type_payload], "next": None},
        )
        intg_route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list", "--type", "Earth_Ranger"])

    assert result.exit_code == 0, result.output
    assert intg_route.calls.last.request.url.params["type"] == type_id


def test_list_unknown_type_exits_2(
    cli_env, auth_token_response, destination_integration_details
):
    # A slug with no matching type → clean exit 2, no integrations request.
    type_payload = destination_integration_details["type"]  # only 'earth_ranger'
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(TYPES_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [type_payload], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list", "--type", "nonexistent"])

    assert result.exit_code == 2, result.output
    assert "unknown integration type" in result.output


def test_list_json_with_type_filter(
    cli_env, auth_token_response, destination_integration_details
):
    # With server-side filtering the integrations endpoint returns only matches.
    type_payload = destination_integration_details["type"]
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(TYPES_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [type_payload], "next": None},
        )
        mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
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


def test_integrations_types_renders_table(
    cli_env, auth_token_response, destination_integration_details
):
    type_payload = destination_integration_details["type"]
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(TYPES_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [type_payload], "next": None},
        )

        result = runner.invoke(app, ["integrations", "types"])

    assert result.exit_code == 0, result.output
    assert "NAME" in result.output and "SLUG" in result.output and "ID" in result.output
    assert "EarthRanger" in result.output
    assert "earth_ranger" in result.output
    assert type_payload["id"] in result.output


def test_integrations_types_json(
    cli_env, auth_token_response, destination_integration_details
):
    type_payload = destination_integration_details["type"]
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(TYPES_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [type_payload], "next": None},
        )

        result = runner.invoke(app, ["integrations", "types", "--json"])

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed[0]["value"] == "earth_ranger"


def test_integrations_types_follows_pagination(
    cli_env,
    auth_token_response,
    destination_integration_details,
    webhook_integration_details,
):
    t1 = destination_integration_details["type"]  # earth_ranger
    t2 = webhook_integration_details["type"]  # liquidtech
    next_url = f"{TYPES_URL}?cursor=2"
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(next_url).respond(
            status_code=httpx.codes.OK, json={"results": [t2], "next": None}
        )
        mock.get(TYPES_URL).respond(
            status_code=httpx.codes.OK, json={"results": [t1], "next": next_url}
        )

        result = runner.invoke(app, ["integrations", "types"])

    assert result.exit_code == 0, result.output
    assert "earth_ranger" in result.output
    assert "liquidtech" in result.output


def test_integrations_types_empty(cli_env, auth_token_response):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(TYPES_URL).respond(
            status_code=httpx.codes.OK, json={"results": [], "next": None}
        )

        result = runner.invoke(app, ["integrations", "types"])

    assert result.exit_code == 0, result.output
    assert "No integration types found" in result.output


def test_list_filter_enabled_true(
    cli_env, auth_token_response, destination_integration_details
):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list", "--enabled"])

    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.params["enabled"] == "true"


def test_list_filter_disabled(
    cli_env, auth_token_response, destination_integration_details
):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list", "--disabled"])

    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.params["enabled"] == "false"


def test_list_without_enabled_flag_omits_param(
    cli_env, auth_token_response, destination_integration_details
):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 0, result.output
    assert "enabled" not in route.calls.last.request.url.params


def test_list_type_and_enabled_combined(
    cli_env, auth_token_response, destination_integration_details
):
    type_payload = destination_integration_details["type"]
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(TYPES_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [type_payload], "next": None},
        )
        intg_route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(
            app, ["integrations", "list", "--type", "earth_ranger", "--enabled"]
        )

    assert result.exit_code == 0, result.output
    params = intg_route.calls.last.request.url.params
    assert params["type"] == type_payload["id"]
    assert params["enabled"] == "true"


def _log_entry(**overrides):
    log = {
        "id": "log-1",
        "created_at": "2026-06-12T09:00:00Z",
        "log_level": 20,
        "log_type": "event",
        "value": "integration_action_started",
        "title": "Action started",
        "integration": {"id": "abc", "name": "ER Site"},
    }
    log.update(overrides)
    return log


def test_logs_by_integration_id(cli_env, auth_token_response):
    integration_id = "338225f3-91f9-4fe1-b013-353a229ce504"
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        route = mock.get(LOGS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [_log_entry()], "next": None},
        )

        result = runner.invoke(app, ["integrations", "logs", integration_id])

    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.params["integration"] == integration_id
    assert "LEVEL" in result.output
    assert "INFO" in result.output  # log_level 20 -> INFO
    assert "Action started" in result.output


def test_logs_json(cli_env, auth_token_response):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(LOGS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [_log_entry()], "next": None},
        )

        result = runner.invoke(app, ["integrations", "logs", "abc", "--json"])

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed[0]["title"] == "Action started"


def test_logs_by_type_uses_server_filter(cli_env, auth_token_response):
    # --type filters server-side via ?integration_type=<slug> in ONE request:
    # no types lookup, no id-gathering, no integration__in chunking.
    integration_id = "338225f3-91f9-4fe1-b013-353a229ce504"
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        logs_route = mock.get(LOGS_URL).respond(
            status_code=httpx.codes.OK,
            json={
                "results": [
                    _log_entry(
                        integration={"id": integration_id, "name": "ER Load Testing"}
                    )
                ],
                "next": None,
            },
        )

        result = runner.invoke(app, ["integrations", "logs", "--type", "earth_ranger"])

    assert result.exit_code == 0, result.output
    params = logs_route.calls.last.request.url.params
    assert params["integration_type"] == "earth_ranger"
    assert "integration__in" not in params
    assert "INTEGRATION" in result.output
    assert "ER Load Testing" in result.output


def test_logs_limit_caps_results(cli_env, auth_token_response):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(LOGS_URL).respond(
            status_code=httpx.codes.OK,
            json={
                "results": [
                    _log_entry(id="1", title="First"),
                    _log_entry(id="2", title="Second"),
                ],
                "next": None,
            },
        )

        result = runner.invoke(app, ["integrations", "logs", "abc", "--limit", "1"])

    assert result.exit_code == 0, result.output
    assert "First" in result.output
    assert "Second" not in result.output


def test_logs_requires_a_target(cli_env, auth_token_response):
    result = runner.invoke(app, ["integrations", "logs"])
    assert result.exit_code == 2, result.output
    assert "exactly one" in result.output.lower()


def test_logs_rejects_both_targets(cli_env, auth_token_response):
    result = runner.invoke(
        app, ["integrations", "logs", "abc", "--type", "earth_ranger"]
    )
    assert result.exit_code == 2, result.output


def test_logs_unknown_type_returns_empty(cli_env, auth_token_response):
    # --type no longer resolves the slug client-side; an unknown/typo'd slug is
    # forwarded to the server, which returns no logs (not a client-side exit 2).
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        logs_route = mock.get(LOGS_URL).respond(
            status_code=httpx.codes.OK, json={"results": [], "next": None}
        )

        result = runner.invoke(app, ["integrations", "logs", "--type", "nope"])

    assert result.exit_code == 0, result.output
    assert "No activity logs found" in result.output
    assert logs_route.calls.last.request.url.params["integration_type"] == "nope"


def test_logs_empty(cli_env, auth_token_response):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(LOGS_URL).respond(
            status_code=httpx.codes.OK, json={"results": [], "next": None}
        )

        result = runner.invoke(app, ["integrations", "logs", "abc"])

    assert result.exit_code == 0, result.output
    assert "No activity logs found" in result.output


def test_list_filter_status(
    cli_env, auth_token_response, destination_integration_details
):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list", "--status", "healthy"])

    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.params["status"] == "healthy"


def test_list_without_status_omits_param(
    cli_env, auth_token_response, destination_integration_details
):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 0, result.output
    assert "status" not in route.calls.last.request.url.params


def test_list_status_composes_with_type_and_enabled(
    cli_env, auth_token_response, destination_integration_details
):
    type_payload = destination_integration_details["type"]
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(TYPES_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [type_payload], "next": None},
        )
        intg_route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(
            app,
            [
                "integrations",
                "list",
                "--type",
                "earth_ranger",
                "--enabled",
                "--status",
                "unhealthy",
            ],
        )

    assert result.exit_code == 0, result.output
    params = intg_route.calls.last.request.url.params
    assert params["type"] == type_payload["id"]
    assert params["enabled"] == "true"
    assert params["status"] == "unhealthy"


def test_list_transport_error_exits_1_clean(cli_env, auth_token_response):
    # A transport-level failure (e.g. connection dropped) must be a clean
    # Error + exit 1, not an uncaught traceback.
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(INTEGRATIONS_URL).mock(
            side_effect=httpx.ReadError("connection dropped")
        )

        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 1, result.output
    assert "Error" in result.output


def test_logs_transport_error_exits_1_clean(cli_env, auth_token_response):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(LOGS_URL).mock(side_effect=httpx.ReadError("connection dropped"))

        result = runner.invoke(app, ["integrations", "logs", "abc"])

    assert result.exit_code == 1, result.output
    assert "Error" in result.output


def test_not_authenticated_message_includes_reason(tmp_path, monkeypatch):
    # When auth fails for a profile, the underlying reason should be shown
    # alongside the `gundi auth login` hint (not swallowed).
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    for var in ("OAUTH_CLIENT_SECRET", "GUNDI_PASSWORD", "GUNDI_USERNAME"):
        monkeypatch.delenv(var, raising=False)
    config_store.add_environment(
        "prod", {"base_url": BASE_URL, "client_id": "c", "token_url": TOKEN_URL}
    )
    config_store.set_active("prod")

    result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 1, result.output
    assert "not authenticated" in result.output.lower()
    assert "gundi auth login" in result.output.lower()
    assert "credentials" in result.output.lower()  # underlying reason surfaced


def test_logs_rejects_non_positive_limit(cli_env):
    result = runner.invoke(app, ["integrations", "logs", "some-id", "--limit", "0"])
    assert result.exit_code == 2, result.output
    assert "limit" in result.output.lower()


def test_run_command_persists_refreshed_token_on_api_error(
    tmp_path, monkeypatch, auth_token_response
):
    # Access token expired but refresh valid: the client refreshes (rotating the
    # token) and THEN the API call fails. The refreshed token must still be
    # persisted so the next invocation isn't left with a stale/rotated token.
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    config_store.add_environment(
        "prod", {"base_url": BASE_URL, "client_id": "c", "token_url": TOKEN_URL}
    )
    config_store.set_active("prod")

    class _Tok:
        access_token = "OLD"
        refresh_token = "R"
        token_type = "Bearer"

    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    future = datetime.now(timezone.utc) + timedelta(hours=12)
    token_store.save_token("prod", _Tok(), past, future)

    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.INTERNAL_SERVER_ERROR, json={"detail": "boom"}
        )

        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 1, result.output
    saved = token_store.load_token("prod")
    assert saved is not None
    assert saved["access_token"] != "OLD"  # refreshed token was persisted


def test_render_logs_table_flattens_multiline_values():
    from gundi_client_v2.cli.integrations import _render_logs_table

    logs = [
        {
            "created_at": "2026-06-12T10:00:00Z",
            "log_level": 40,
            "log_type": "event",
            "value": "line1\nline2",
            "title": "a\nb",
        }
    ]
    out = _render_logs_table(logs)
    # Header + exactly one data row must be two physical lines (no embedded newlines).
    assert len(out.splitlines()) == 2
    assert "line1 line2" in out


def test_list_env_missing_required_key_exits_2(tmp_path, monkeypatch):
    # Hand-edited env missing client_id must fail cleanly, not traceback.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    config_store.save_config(
        {
            "active": "prod",
            "environments": {"prod": {"base_url": BASE_URL, "token_url": TOKEN_URL}},
        }
    )
    result = runner.invoke(app, ["integrations", "list"])
    assert result.exit_code == 2, result.output
    assert "Traceback" not in result.output


def test_run_command_token_persist_failure_is_best_effort(
    tmp_path, monkeypatch, auth_token_response, destination_integration_details
):
    # If caching a refreshed token fails, the command still succeeds (exit 0)
    # with a warning — the finally-persist must not mask the primary outcome.
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    config_store.add_environment(
        "prod", {"base_url": BASE_URL, "client_id": "c", "token_url": TOKEN_URL}
    )
    config_store.set_active("prod")

    class _Tok:
        access_token = "OLD"
        refresh_token = "R"
        token_type = "Bearer"

    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    future = datetime.now(timezone.utc) + timedelta(hours=12)
    token_store.save_token("prod", _Tok(), past, future)  # real setup save

    def _boom(*a, **k):
        raise config_store.ConfigError("cannot cache")

    monkeypatch.setattr(token_store, "save_token", _boom)  # subsequent saves fail

    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )
        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 0, result.output
    assert destination_integration_details["id"] in result.output
    assert "Traceback" not in result.output


def test_logs_level_filter_forwards_log_level(cli_env, auth_token_response):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        route = mock.get(LOGS_URL).respond(
            status_code=httpx.codes.OK, json={"results": [_log_entry()], "next": None}
        )
        result = runner.invoke(
            app, ["integrations", "logs", "id-1", "--level", "error"]
        )
    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.params["log_level"] == "40"


def test_logs_level_is_case_insensitive(cli_env, auth_token_response):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        route = mock.get(LOGS_URL).respond(
            status_code=httpx.codes.OK, json={"results": [_log_entry()], "next": None}
        )
        result = runner.invoke(
            app, ["integrations", "logs", "id-1", "--level", "Warning"]
        )
    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.params["log_level"] == "30"


def test_logs_invalid_level_exits_2(cli_env):
    result = runner.invoke(app, ["integrations", "logs", "id-1", "--level", "bogus"])
    assert result.exit_code == 2, result.output
    assert "level" in result.output.lower()


def test_logs_origin_filter_forwards(cli_env, auth_token_response):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        route = mock.get(LOGS_URL).respond(
            status_code=httpx.codes.OK, json={"results": [_log_entry()], "next": None}
        )
        result = runner.invoke(
            app, ["integrations", "logs", "id-1", "--origin", "dispatcher"]
        )
    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.params["origin"] == "dispatcher"


def test_logs_since_until_forwards_dates(cli_env, auth_token_response):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        route = mock.get(LOGS_URL).respond(
            status_code=httpx.codes.OK, json={"results": [_log_entry()], "next": None}
        )
        result = runner.invoke(
            app,
            [
                "integrations",
                "logs",
                "id-1",
                "--since",
                "2026-07-01",
                "--until",
                "2026-07-06",
            ],
        )
    assert result.exit_code == 0, result.output
    params = route.calls.last.request.url.params
    assert params["from_date"] == "2026-07-01"
    assert params["to_date"] == "2026-07-06"


def test_logs_invalid_date_exits_2(cli_env):
    result = runner.invoke(
        app, ["integrations", "logs", "id-1", "--since", "last-tuesday"]
    )
    assert result.exit_code == 2, result.output
    assert "date" in result.output.lower()


def test_logs_filters_forwarded_on_type_path(cli_env, auth_token_response):
    integration_id = "338225f3-91f9-4fe1-b013-353a229ce504"
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        logs_route = mock.get(LOGS_URL).respond(
            status_code=httpx.codes.OK,
            json={
                "results": [
                    _log_entry(integration={"id": integration_id, "name": "x"})
                ],
                "next": None,
            },
        )
        result = runner.invoke(
            app, ["integrations", "logs", "--type", "earth_ranger", "--level", "error"]
        )
    assert result.exit_code == 0, result.output
    last = logs_route.calls.last.request.url.params
    assert last["log_level"] == "40"
    assert last["integration_type"] == "earth_ranger"


def test_list_by_type_clean_error_on_unparseable_type(
    cli_env, auth_token_response, destination_integration_details
):
    # A type whose `value` violates gundi_core's slug regex (^[a-z0-9_]+$) makes
    # parse_obj_as(List[IntegrationType], ...) raise while resolving --type. One
    # bad type must surface a clean CLI error (exit 1), not a raw traceback.
    from pydantic import ValidationError

    good_type = destination_integration_details["type"]
    bad_type = {
        **good_type,
        "id": "9f000000-0000-0000-0000-0000000000bd",
        "name": "Kenwood Radios",
        "value": "kenwood-radios",  # hyphen -> fails ^[a-z0-9_]+$
    }
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(TYPES_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [good_type, bad_type], "next": None},
        )
        result = runner.invoke(app, ["integrations", "list", "--type", "earth_ranger"])

    assert result.exit_code == 1, result.output
    assert "Error:" in result.output
    # The clean-error message contract, on one line, with no traceback leaked.
    assert "could not parse" in result.output
    assert "Traceback" not in result.output
    # The pydantic ValidationError must be handled, not propagated.
    assert not isinstance(result.exception, ValidationError), result.output
