"""`gundi integrations` commands: list, enable, disable."""

import json
from typing import List, Optional

import typer

from gundi_core.schemas.v2 import Integration, LogLevel

from ._client import run_command

integrations_app = typer.Typer(
    help="List and manage Gundi integrations.", no_args_is_help=True
)


@integrations_app.command("list")
def list_integrations(
    integration_type: Optional[str] = typer.Option(
        None, "--type", help="Filter by integration type slug (e.g. earth_ranger)."
    ),
    enabled: Optional[bool] = typer.Option(
        None,
        "--enabled/--disabled",
        help="Show only enabled (--enabled) or only disabled (--disabled). Default: all.",
    ),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        help="Filter by health status (e.g. healthy, unhealthy, disabled).",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit JSON instead of a table (pipe to jq)."
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Environment to use (overrides the active one)."
    ),
) -> None:
    """List integrations, optionally filtered by type, enabled state, and/or status."""

    async def _fetch(client):
        params = {}
        if integration_type:
            # The API filters `type` by UUID, not slug, so resolve the slug to
            # the type's id and filter server-side.
            params["type"] = await _resolve_type_id(client, integration_type)
        if enabled is not None:
            params["enabled"] = "true" if enabled else "false"
        if status:
            params["status"] = status
        return [i async for i in client.get_integrations(params=params or None)]

    integrations = run_command(profile, _fetch)

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


@integrations_app.command("types")
def list_integration_types(
    json_output: bool = typer.Option(
        False, "--json", help="Emit JSON instead of a table (pipe to jq)."
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Environment to use (overrides the active one)."
    ),
) -> None:
    """List the integration types available in Gundi."""

    async def _fetch(client):
        return [t async for t in client.get_integration_types()]

    types = run_command(profile, _fetch)

    if json_output:
        typer.echo(json.dumps([t.dict() for t in types], default=str, indent=2))
        return
    if not types:
        typer.echo("No integration types found.", err=True)
        return
    typer.echo(_render_types_table(types))


@integrations_app.command("logs")
def integration_logs(
    integration_id: Optional[str] = typer.Argument(
        None, help="UUID of the integration to read logs for."
    ),
    integration_type: Optional[str] = typer.Option(
        None,
        "--type",
        help="Type slug; show logs across all integrations of this type.",
    ),
    limit: int = typer.Option(
        50, "--limit", help="Maximum number of latest logs to show."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit JSON instead of a table (pipe to jq)."
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Environment to use (overrides the active one)."
    ),
) -> None:
    """Show the latest activity logs for an integration or an integration type."""
    if (integration_id is None) == (integration_type is None):
        typer.echo(
            "Error: provide an integration id or --type (exactly one).", err=True
        )
        raise typer.Exit(2)

    async def _fetch(client):
        if integration_type is None:
            return await _fetch_logs(client, {"integration": integration_id}, limit)
        # By type: there's no type filter on logs, so gather the type's
        # integration ids and filter by `integration__in`. The ids are chunked
        # across requests so the query string stays under the server's
        # request-line limit, then merged newest-first.
        type_id = await _resolve_type_id(client, integration_type)
        ids = [
            str(i.id) async for i in client.get_integrations(params={"type": type_id})
        ]
        if not ids:
            return []
        collected = []
        for chunk in _chunked(ids, _INTEGRATION_IN_CHUNK):
            collected.extend(
                await _fetch_logs(client, {"integration__in": ",".join(chunk)}, limit)
            )
        collected.sort(key=lambda log: log.get("created_at") or "", reverse=True)
        return collected[:limit]

    logs = run_command(profile, _fetch)

    if json_output:
        typer.echo(json.dumps(logs, default=str, indent=2))
        return
    if not logs:
        typer.echo("No activity logs found.", err=True)
        return
    typer.echo(
        _render_logs_table(logs, include_integration=integration_type is not None)
    )


def _set_enabled(integration_id: str, enabled: bool, profile: Optional[str]) -> None:
    async def _update(client):
        return await client.update_integration(integration_id, {"enabled": enabled})

    integration = run_command(profile, _update)
    state = "enabled" if integration.enabled else "disabled"
    typer.echo(f"Integration {integration.id} ({integration.name}) is now {state}.")


def _render_table(integrations: List[Integration]) -> str:
    """Render integrations as a plain-text aligned table."""
    header = ("ID", "NAME", "TYPE", "ENABLED", "STATUS")
    rows = [
        (
            str(i.id),
            i.name or "",
            i.type.value if i.type else "",
            "true" if i.enabled else "false",
            i.status or "",
        )
        for i in integrations
    ]
    return _format_table(header, rows)


# Integration ids per `integration__in` request. UUIDs are 36 chars + a comma,
# so 40 keeps the query well under the server's 2048-byte request-line limit.
_INTEGRATION_IN_CHUNK = 40


def _chunked(items: list, size: int):
    """Yield successive ``size``-length slices of ``items``."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


async def _fetch_logs(client, params: dict, limit: int) -> list:
    """Collect up to ``limit`` activity logs (newest-first) for ``params``."""
    logs = []
    async for log in client.get_activity_logs(params=params):
        logs.append(log)
        if len(logs) >= limit:
            break
    return logs


async def _resolve_type_id(client, slug: str) -> str:
    """Resolve an integration type slug (``value``) to its UUID.

    Exits 2 with a clear message if no type matches (case-insensitive).
    """
    wanted = slug.lower()
    async for itype in client.get_integration_types():
        if itype.value and itype.value.lower() == wanted:
            return str(itype.id)
    typer.echo(f"Error: unknown integration type '{slug}'.", err=True)
    raise typer.Exit(2)


def _log_level_name(level) -> str:
    """Map an integer log level to its name (DEBUG/INFO/WARNING/ERROR)."""
    try:
        return LogLevel(level).name
    except (ValueError, TypeError):
        return "" if level is None else str(level)


def _render_logs_table(logs: list, include_integration: bool = False) -> str:
    """Render activity logs as a plain-text aligned table."""
    header = ("CREATED_AT", "LEVEL", "TYPE", "VALUE", "TITLE")
    if include_integration:
        header = header + ("INTEGRATION",)
    rows = []
    for log in logs:
        row = (
            str(log.get("created_at") or ""),
            _log_level_name(log.get("log_level")),
            str(log.get("log_type") or ""),
            str(log.get("value") or ""),
            str(log.get("title") or ""),
        )
        if include_integration:
            integration = log.get("integration") or {}
            row = row + (str(integration.get("name") or ""),)
        rows.append(row)
    return _format_table(header, rows)


def _render_types_table(types: list) -> str:
    """Render integration types as a plain-text aligned table."""
    header = ("NAME", "SLUG", "ID")
    rows = [(t.name or "", t.value or "", str(t.id)) for t in types]
    return _format_table(header, rows)


def _format_table(header: tuple, rows: list) -> str:
    """Render a header + rows as a plain-text, column-aligned table."""
    all_rows = [header, *rows]
    widths = [max(len(row[col]) for row in all_rows) for col in range(len(header))]
    return "\n".join(
        "  ".join(cell.ljust(widths[col]) for col, cell in enumerate(row))
        for row in all_rows
    )
