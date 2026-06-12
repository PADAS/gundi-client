"""Shared CLI helpers: build a client from the environment and run commands.

``build_client()`` mirrors the env-var conventions documented in the examples
(client_credentials grant). ``run_with_client()`` bridges Typer's sync command
functions to the async ``GundiClient`` and maps API/auth failures to clean
error messages with conventional exit codes.
"""

import asyncio
import os
from typing import Awaitable, Callable, TypeVar

import typer

from gundi_client_v2 import GundiClient
from gundi_client_v2.errors import AuthenticationError, GundiAPIError

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
