"""`gundi auth` commands: login (cache a token), logout, status."""

import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
import typer

from gundi_client_v2.errors import AuthenticationError, GundiAPIError

from . import config_store, token_store
from ._client import active_env_name, build_client_for_login

auth_app = typer.Typer(
    help="Authenticate and manage cached tokens.", no_args_is_help=True
)


@auth_app.command("login")
def login(
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Environment to log in to."
    ),
    username: Optional[str] = typer.Option(
        None,
        "--username",
        "-u",
        help="Username for the password grant (also reads GUNDI_USERNAME).",
    ),
) -> None:
    """Obtain and cache an OAuth token for the selected environment."""
    env_name = active_env_name(profile)
    client = build_client_for_login(env_name, username=username)

    async def _authenticate():
        async with client:
            await client.get_access_token(force_refresh_token=True)

    try:
        asyncio.run(_authenticate())
    except (AuthenticationError, GundiAPIError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)
    except httpx.HTTPError as exc:
        typer.echo(f"Error: request failed: {exc}", err=True)
        raise typer.Exit(1)

    token_store.save_token(
        env_name,
        client.cached_token,
        client.cached_token_expires_at,
        client.cached_token_refresh_expires_at,
    )
    # Persist a newly supplied username (non-secret) so future logins and
    # commands treat this as a password-grant environment without the flag.
    supplied = username or os.environ.get("GUNDI_USERNAME")
    if supplied:
        env = config_store.get_environment(env_name)
        if env.get("username") != supplied:
            config_store.add_environment(env_name, {**env, "username": supplied})
    typer.echo(f"Authenticated. Token cached for '{env_name}'.")


@auth_app.command("logout")
def logout(
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Environment to log out of."
    ),
) -> None:
    """Delete the cached token for the selected environment."""
    env_name = active_env_name(profile)
    typer.echo(
        "Logged out." if token_store.delete_token(env_name) else "No cached token."
    )


@auth_app.command("status")
def status(
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Environment to check."
    ),
) -> None:
    """Report whether a valid cached token exists."""
    env_name = active_env_name(profile)
    data = token_store.load_token(env_name)
    if not data:
        typer.echo(f"{env_name}: not authenticated")
        return
    expires_at = datetime.fromisoformat(data["expires_at"])
    state = "valid" if expires_at > datetime.now(timezone.utc) else "expired"
    typer.echo(f"{env_name}: {state} (access token expires {expires_at.isoformat()})")
