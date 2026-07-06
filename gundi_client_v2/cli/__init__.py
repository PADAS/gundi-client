"""Command-line interface for the Gundi API.

Exposes the ``gundi`` console command. Typer is an optional dependency
(the ``cli`` extra), so importing this package without it installed yields a
fallback ``app`` that prints an install hint rather than an ImportError.
"""

try:
    import typer  # noqa: F401
except ImportError:  # pragma: no cover - exercised only without the cli extra
    import sys

    def app(*args, **kwargs) -> None:
        print(
            'Error: the "gundi" CLI requires extra dependencies. '
            'Install them with: pip install "gundi-client-v2[cli]"',
            file=sys.stderr,
        )
        raise SystemExit(1)

else:
    from .main import app

__all__ = ["app"]
