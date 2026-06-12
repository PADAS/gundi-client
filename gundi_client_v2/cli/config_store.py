"""Persistent CLI configuration: named environments stored under XDG config.

Stores only non-secret connection config in ``config.json``. Secrets are never
written here (see token_store for cached tokens). All files are user-private.
"""

import json
import os
from pathlib import Path


class ConfigError(Exception):
    """Raised for missing/unknown environments or unreadable config."""


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "gundi"


def config_file() -> Path:
    return config_dir() / "config.json"


def tokens_dir() -> Path:
    return config_dir() / "tokens"


def ensure_dir(path: Path) -> None:
    """Create ``path`` (and parents) private to the user (0700)."""
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def load_config() -> dict:
    path = config_file()
    if not path.exists():
        return {"active": None, "environments": {}}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigError(f"could not read config at {path}: {exc}")


def save_config(config: dict) -> None:
    ensure_dir(config_dir())
    path = config_file()
    path.write_text(json.dumps(config, indent=2))
    os.chmod(path, 0o600)
