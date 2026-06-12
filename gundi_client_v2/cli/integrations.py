"""`gundi integrations` commands: list, enable, disable."""

import json
from typing import List, Optional

import typer

from gundi_core.schemas.v2 import Integration

from ._client import run_command

integrations_app = typer.Typer(
    help="List and manage Gundi integrations.", no_args_is_help=True
)


@integrations_app.command("list")
def list_integrations(
    integration_type: Optional[str] = typer.Option(
        None, "--type", help="Filter by integration type slug (e.g. earth_ranger)."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit JSON instead of a table (pipe to jq)."
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Environment to use (overrides the active one)."
    ),
) -> None:
    """List integrations, optionally filtered by type."""

    async def _fetch(client):
        return [i async for i in client.get_integrations()]

    integrations = run_command(profile, _fetch)

    # The API's `type` filter matches the type UUID, not the slug, so filter by
    # the type's slug (`type.value`) client-side, case-insensitively.
    if integration_type:
        wanted = integration_type.lower()
        integrations = [
            i for i in integrations if i.type and i.type.value.lower() == wanted
        ]

    if json_output:
        typer.echo(json.dumps([i.dict() for i in integrations], default=str, indent=2))
        return
    if not integrations:
        typer.echo("No integrations found.", err=True)
        return
    typer.echo(_render_table(integrations))


@integrations_app.command("enable")
def enable_integration(
    integration_id: str = typer.Argument(
        ..., help="UUID of the integration to enable."
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Environment to use (overrides the active one)."
    ),
) -> None:
    """Enable an integration."""
    _set_enabled(integration_id, True, profile)


@integrations_app.command("disable")
def disable_integration(
    integration_id: str = typer.Argument(
        ..., help="UUID of the integration to disable."
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Environment to use (overrides the active one)."
    ),
) -> None:
    """Disable an integration."""
    _set_enabled(integration_id, False, profile)


def _set_enabled(integration_id: str, enabled: bool, profile: Optional[str]) -> None:
    async def _update(client):
        return await client.update_integration(integration_id, {"enabled": enabled})

    integration = run_command(profile, _update)
    state = "enabled" if integration.enabled else "disabled"
    typer.echo(f"Integration {integration.id} ({integration.name}) is now {state}.")


def _render_table(integrations: List[Integration]) -> str:
    """Render integrations as a plain-text aligned table."""
    header = ("ID", "NAME", "TYPE", "ENABLED", "STATUS")
    rows = [header]
    for i in integrations:
        rows.append(
            (
                str(i.id),
                i.name or "",
                i.type.value if i.type else "",
                "true" if i.enabled else "false",
                i.status or "",
            )
        )
    widths = [max(len(row[col]) for row in rows) for col in range(len(header))]
    return "\n".join(
        "  ".join(cell.ljust(widths[col]) for col, cell in enumerate(row))
        for row in rows
    )
