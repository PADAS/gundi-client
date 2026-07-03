"""Shared CLI helpers: build a client from the environment and run commands.

``build_client()`` mirrors the env-var conventions documented in the examples
(client_credentials grant). ``run_with_client()`` bridges Typer's sync command
functions to the async ``GundiClient`` and maps API/auth failures to clean
error messages with conventional exit codes.
"""

import asyncio
import os
from typing import Awaitable, Callable, Optional, TypeVar

import httpx
import typer

from gundi_client_v2 import GundiClient
from gundi_client_v2.errors import AuthenticationError, GundiAPIError

from . import config_store, token_store

T = TypeVar("T")

# env var -> GundiClient kwarg. Always required.
_REQUIRED_ENV = {
    "GUNDI_API_BASE_URL": "base_url",
    "OAUTH_CLIENT_ID": "oauth_client_id",
}


def build_client() -> GundiClient:
    """Construct a GundiClient from environment variables.

    Mirrors the library's auth rules. A ``client_id`` is always required, plus:

    - **Credentials** — either ``GUNDI_USERNAME`` + ``GUNDI_PASSWORD`` (password
      grant, public client) or ``OAUTH_CLIENT_SECRET`` (client-credentials,
      confidential client). When both are present the client uses the password
      grant.
    - **Token endpoint** — ``OAUTH_ISSUER`` (preferred; resolved via OIDC
      discovery, IdP-agnostic) or an explicit ``OAUTH_TOKEN_URL``. When both are
      set, the explicit URL wins.

    ``OAUTH_AUDIENCE`` is forwarded when set (some IdPs require it). Exits with
    code 2, listing what's missing, when required configuration is absent.
    """
    kwargs = {}
    missing = []
    for env_name, kwarg in _REQUIRED_ENV.items():
        if value := os.environ.get(env_name):
            kwargs[kwarg] = value
        else:
            missing.append(env_name)

    # Credentials: password grant (username + password) or client-credentials
    # (client_secret). At least one full set is required.
    username = os.environ.get("GUNDI_USERNAME")
    password = os.environ.get("GUNDI_PASSWORD")
    client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
    if username:
        kwargs["username"] = username
    if password:
        kwargs["password"] = password
    if client_secret:
        kwargs["oauth_client_secret"] = client_secret
    if not (username and password) and not client_secret:
        missing.append("OAUTH_CLIENT_SECRET (or GUNDI_USERNAME + GUNDI_PASSWORD)")

    # Token endpoint: discovery via OAUTH_ISSUER preferred, OAUTH_TOKEN_URL is
    # the explicit fallback. The client prefers oauth_token_url when both exist.
    if issuer := os.environ.get("OAUTH_ISSUER"):
        kwargs["oauth_issuer"] = issuer
    if token_url := os.environ.get("OAUTH_TOKEN_URL"):
        kwargs["oauth_token_url"] = token_url
    if not issuer and not token_url:
        missing.append("OAUTH_ISSUER (or OAUTH_TOKEN_URL)")

    if missing:
        typer.echo(f"Error: missing required env vars: {', '.join(missing)}", err=True)
        raise typer.Exit(2)
    if audience := os.environ.get("OAUTH_AUDIENCE"):
        kwargs["oauth_audience"] = audience
    return GundiClient(**kwargs)


def run_with_client(async_fn: Callable[[GundiClient], Awaitable[T]]) -> T:
    """Run ``async_fn(client)`` inside an open client, mapping errors to exits.

    AuthenticationError / GundiAPIError are rendered as ``Error: ...`` on stderr
    with exit code 1; unexpected exceptions propagate.
    """
    client = build_client()  # may raise typer.Exit(2)

    async def _runner() -> T:
        async with client:
            return await async_fn(client)

    try:
        return asyncio.run(_runner())
    except (AuthenticationError, GundiAPIError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)
    except httpx.HTTPError as exc:
        typer.echo(f"Error: request failed: {exc}", err=True)
        raise typer.Exit(1)


def resolve_environment(profile: Optional[str]) -> Optional[str]:
    """Resolve the active environment name, or None to use raw env vars.

    Precedence: explicit ``profile`` > ``GUNDI_PROFILE`` > stored active > None.
    Raises ConfigError if a named environment does not exist.
    """
    name = profile or os.environ.get("GUNDI_PROFILE") or config_store.get_active()
    if name:
        config_store.get_environment(name)  # validate; raises ConfigError
    return name


def active_env_name(profile: Optional[str]) -> str:
    """Like resolve_environment, but for commands that require a profile.

    Exits 2 with guidance when no environment is selected.
    """
    name = profile or os.environ.get("GUNDI_PROFILE") or config_store.get_active()
    if not name:
        typer.echo(
            "Error: no environment selected. Run `gundi env use <name>` or pass --profile.",
            err=True,
        )
        raise typer.Exit(2)
    try:
        config_store.get_environment(name)  # validate it exists
    except config_store.ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2)
    return name


def _client_kwargs_from_env(env: dict) -> dict:
    kwargs = {"base_url": env["base_url"], "oauth_client_id": env["client_id"]}
    if v := env.get("issuer"):
        kwargs["oauth_issuer"] = v
    if v := env.get("token_url"):
        kwargs["oauth_token_url"] = v
    if v := env.get("audience"):
        kwargs["oauth_audience"] = v
    if v := env.get("username"):
        kwargs["username"] = v
    if v := env.get("scope"):
        kwargs["oauth_scope"] = v
    return kwargs


def _build_profile_client(env: dict) -> GundiClient:
    """Client from a profile's config, plus any secrets available in env vars.

    Supplying env secrets (when present) lets the client authenticate implicitly
    on a cache miss and refresh client-credentials tokens; they are optional.
    """
    kwargs = _client_kwargs_from_env(env)
    if env.get("username") and (pw := os.environ.get("GUNDI_PASSWORD")):
        kwargs["password"] = pw
    if secret := os.environ.get("OAUTH_CLIENT_SECRET"):
        kwargs["oauth_client_secret"] = secret
    return GundiClient(**kwargs)


def build_client_for_login(
    env_name: str, username: Optional[str] = None
) -> GundiClient:
    """Client for `gundi auth login`: config + a secret from env or a hidden prompt.

    Grant is chosen by username availability: a username from the ``username``
    argument, the stored profile, or ``GUNDI_USERNAME`` means password grant
    (prompt for password); otherwise client-credentials (prompt for secret).
    """
    env = config_store.get_environment(env_name)
    kwargs = _client_kwargs_from_env(env)
    resolved_username = (
        username or env.get("username") or os.environ.get("GUNDI_USERNAME")
    )
    if resolved_username:
        kwargs["username"] = resolved_username
        kwargs["password"] = os.environ.get("GUNDI_PASSWORD") or typer.prompt(
            "Password", hide_input=True
        )
    else:
        kwargs["oauth_client_secret"] = os.environ.get(
            "OAUTH_CLIENT_SECRET"
        ) or typer.prompt("Client secret", hide_input=True)
    return GundiClient(**kwargs)


def run_command(
    profile: Optional[str], async_fn: Callable[[GundiClient], Awaitable[T]]
) -> T:
    """Resolve the environment, restore any cached token, run, persist, map errors."""
    try:
        env_name = resolve_environment(profile)
    except config_store.ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2)

    if env_name is None:
        # Backward-compatible raw-env path (no profile configured).
        return run_with_client(async_fn)

    client = _build_profile_client(config_store.get_environment(env_name))
    cached = token_store.load_token(env_name)
    if cached:
        token_store.apply_to_client(client, cached)
    had_token = client.cached_token is not None
    before = client.cached_token.access_token if client.cached_token else None

    async def _runner() -> T:
        async with client:
            return await async_fn(client)

    def _persist_token() -> None:
        # Persist a newly obtained or rotated token. Runs on both success and
        # error paths: the token may have been refreshed (and the refresh token
        # rotated) before a later API/transport failure, and losing it would
        # break transparent refresh on the next invocation.
        if client.cached_token and (
            not had_token or client.cached_token.access_token != before
        ):
            token_store.save_token(
                env_name,
                client.cached_token,
                client.cached_token_expires_at,
                client.cached_token_refresh_expires_at,
            )

    try:
        result = asyncio.run(_runner())
    except AuthenticationError as exc:
        suffix = f" --profile {env_name}" if profile else ""
        detail = f" ({exc})" if str(exc) else ""
        typer.echo(
            f"Error: not authenticated for '{env_name}'{detail}. "
            f"Run `gundi auth login{suffix}`.",
            err=True,
        )
        raise typer.Exit(1)
    except GundiAPIError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)
    except httpx.HTTPError as exc:
        typer.echo(f"Error: request failed: {exc}", err=True)
        raise typer.Exit(1)
    finally:
        _persist_token()

    return result
