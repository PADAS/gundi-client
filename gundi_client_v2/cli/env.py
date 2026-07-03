"""`gundi env` commands: manage named environments."""

import json
from typing import Optional

import typer

from . import config_store, token_store

env_app = typer.Typer(help="Manage named Gundi environments.", no_args_is_help=True)


@env_app.command("add")
def add_env(
    name: str = typer.Argument(..., help="Environment name (e.g. prod, dev)."),
    base_url: str = typer.Option(..., "--base-url", help="Gundi API base URL."),
    client_id: str = typer.Option(..., "--client-id", help="OAuth client id."),
    issuer: Optional[str] = typer.Option(
        None, "--issuer", help="OIDC issuer URL (discovery)."
    ),
    token_url: Optional[str] = typer.Option(
        None, "--token-url", help="Explicit OAuth token URL."
    ),
    audience: Optional[str] = typer.Option(None, "--audience", help="OAuth audience."),
    username: Optional[str] = typer.Option(
        None, "--username", help="Username (password grant)."
    ),
    scope: Optional[str] = typer.Option(None, "--scope", help="OAuth scope."),
    activate: bool = typer.Option(
        False, "--activate", help="Make this the active environment."
    ),
) -> None:
    """Add or overwrite a named environment."""
    if not issuer and not token_url:
        typer.echo("Error: provide --issuer or --token-url.", err=True)
        raise typer.Exit(2)
    env = {"base_url": base_url, "client_id": client_id}
    for key, value in (
        ("issuer", issuer),
        ("token_url", token_url),
        ("audience", audience),
        ("username", username),
        ("scope", scope),
    ):
        if value:
            env[key] = value
    try:
        config_store.add_environment(name, env)
        if activate:
            config_store.set_active(name)
    except config_store.ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2)
    typer.echo(f"Environment '{name}' saved.")


@env_app.command("list")
def list_envs() -> None:
    """List environments; the active one is marked with `*`."""
    try:
        config = config_store.load_config()
    except config_store.ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2)
    environments = config.get("environments", {})
    if not environments:
        typer.echo("No environments configured.", err=True)
        return
    active = config.get("active")
    for name in environments:
        typer.echo(f"{'*' if name == active else ' '} {name}")


@env_app.command("show")
def show_env(
    name: Optional[str] = typer.Argument(
        None, help="Environment to show (default: active)."
    ),
) -> None:
    """Print one environment's config (no secrets are stored)."""
    try:
        target = name or config_store.get_active()
        if not target:
            typer.echo("Error: no environment specified or active.", err=True)
            raise typer.Exit(2)  # typer.Exit is BaseException; not caught below

        env = config_store.get_environment(target)
    except config_store.ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2)
    typer.echo(json.dumps(env, indent=2))


@env_app.command("use")
def use_env(name: str = typer.Argument(..., help="Environment to activate.")) -> None:
    """Set the active environment."""
    try:
        config_store.set_active(name)
    except config_store.ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2)
    typer.echo(f"Active environment set to '{name}'.")


@env_app.command("remove")
def remove_env(name: str = typer.Argument(..., help="Environment to remove.")) -> None:
    """Remove an environment and its cached token."""
    try:
        config_store.remove_environment(name)
    except config_store.ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2)
    token_store.delete_token(name)
    typer.echo(f"Environment '{name}' removed.")
