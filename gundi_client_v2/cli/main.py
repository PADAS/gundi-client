"""Typer application wiring for the `gundi` CLI."""

import typer

from .integrations import integrations_app

app = typer.Typer(
    help="Command-line interface for the Gundi API.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(integrations_app, name="integrations")
