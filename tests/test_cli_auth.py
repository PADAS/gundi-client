import httpx
import pytest
import respx
from typer.testing import CliRunner

from gundi_client_v2.cli import app, config_store, token_store

runner = CliRunner()

ISSUER = "https://fakeauth.com/auth/realms/dev"
TOKEN_URL = f"{ISSUER}/protocol/openid-connect/token"


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    for var in ("OAUTH_CLIENT_SECRET", "GUNDI_PASSWORD", "GUNDI_USERNAME"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def _add_cc_env():
    config_store.add_environment(
        "prod", {"base_url": "https://api.x", "client_id": "c", "token_url": TOKEN_URL}
    )
    config_store.set_active("prod")


def test_login_caches_token_from_env_secret(auth_token_response, monkeypatch):
    _add_cc_env()
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "shhh")
    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        result = runner.invoke(app, ["auth", "login"])
    assert result.exit_code == 0, result.output
    assert token_store.load_token("prod") is not None


def test_login_username_flag_uses_password_grant(auth_token_response, monkeypatch):
    _add_cc_env()  # env has NO stored username
    monkeypatch.setenv("GUNDI_PASSWORD", "hunter2")
    with respx.mock(assert_all_called=False) as mock:
        token_route = mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        result = runner.invoke(app, ["auth", "login", "--username", "me@example.com"])
    assert result.exit_code == 0, result.output
    assert token_store.load_token("prod") is not None
    body = token_route.calls.last.request.content.decode()
    assert "grant_type=password" in body
    assert "username=me%40example.com" in body


def test_login_username_env_var_uses_password_grant(auth_token_response, monkeypatch):
    _add_cc_env()
    monkeypatch.setenv("GUNDI_USERNAME", "me@example.com")
    monkeypatch.setenv("GUNDI_PASSWORD", "hunter2")
    with respx.mock(assert_all_called=False) as mock:
        token_route = mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        result = runner.invoke(app, ["auth", "login"])
    assert result.exit_code == 0, result.output
    body = token_route.calls.last.request.content.decode()
    assert "grant_type=password" in body


def test_login_username_flag_persisted_to_env(auth_token_response, monkeypatch):
    _add_cc_env()
    monkeypatch.setenv("GUNDI_PASSWORD", "hunter2")
    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        runner.invoke(app, ["auth", "login", "--username", "me@example.com"])
    assert config_store.get_environment("prod").get("username") == "me@example.com"


def test_login_prompts_for_password_when_username_given(auth_token_response):
    _add_cc_env()  # no GUNDI_PASSWORD in env -> hidden prompt
    with respx.mock(assert_all_called=False) as mock:
        token_route = mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        result = runner.invoke(
            app, ["auth", "login", "--username", "me@example.com"], input="s3cret\n"
        )
    assert result.exit_code == 0, result.output
    body = token_route.calls.last.request.content.decode()
    assert "grant_type=password" in body


def test_login_without_secret_prompts(auth_token_response):
    _add_cc_env()
    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        result = runner.invoke(app, ["auth", "login"], input="prompted-secret\n")
    assert result.exit_code == 0, result.output
    assert token_store.load_token("prod") is not None


def test_logout_deletes_token(auth_token_response, monkeypatch):
    _add_cc_env()
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "shhh")
    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        runner.invoke(app, ["auth", "login"])
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert token_store.load_token("prod") is None


def test_status_reports_not_authenticated():
    _add_cc_env()
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 0
    assert "not authenticated" in result.output.lower()


def test_login_no_active_env_exits_2():
    result = runner.invoke(app, ["auth", "login"])
    assert result.exit_code == 2
    assert "no environment selected" in result.output.lower()


def test_status_reports_valid_after_login(auth_token_response, monkeypatch):
    _add_cc_env()
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "shhh")
    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        runner.invoke(app, ["auth", "login"])
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_status_dangling_active_env_exits_2():
    # The stored active environment points at a name with no config entry
    # (e.g. a hand-edited/corrupted config). This must fail cleanly, not silently.
    config_store.save_config({"active": "ghost", "environments": {}})
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 2
    assert "unknown environment" in result.output.lower()


def test_login_network_error_exits_1_clean(monkeypatch):
    _add_cc_env()
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "shhh")
    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).mock(side_effect=httpx.ConnectError("boom"))
        result = runner.invoke(app, ["auth", "login"])
    assert result.exit_code == 1, result.output
    assert "Error" in result.output
    assert "Traceback" not in result.output


def test_login_malformed_2xx_exits_1_clean(monkeypatch):
    _add_cc_env()
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "shhh")
    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, text="<html>nope</html>"
        )
        result = runner.invoke(app, ["auth", "login"])
    assert result.exit_code == 1, result.output
    assert "Error" in result.output
    assert "Traceback" not in result.output


def test_status_reports_expired(monkeypatch):
    from datetime import datetime, timedelta, timezone

    _add_cc_env()

    class _Tok:
        access_token = "AT"
        refresh_token = "R"
        token_type = "Bearer"

    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token_store.save_token("prod", _Tok(), past, past)
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 0, result.output
    assert "expired" in result.output.lower()


def test_login_env_missing_required_key_exits_2(monkeypatch):
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "shhh")
    config_store.save_config(
        {
            "active": "prod",
            "environments": {
                "prod": {"base_url": "https://api.x", "token_url": TOKEN_URL}
            },
        }
    )
    result = runner.invoke(app, ["auth", "login"])
    assert result.exit_code == 2, result.output
    assert "Traceback" not in result.output
