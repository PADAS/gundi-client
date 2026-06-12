"""Persistent CLI configuration: named environments stored under XDG config.

Stores only non-secret connection config in ``config.json``. Secrets are never
written here (see token_store for cached tokens). All files are user-private.
"""

import json
import os
from pathlib import Path
from typing import Optional


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


def add_environment(name: str, env: dict) -> None:
    config = load_config()
    config.setdefault("environments", {})[name] = env
    save_config(config)


def get_environment(name: str) -> dict:
    envs = load_config().get("environments", {})
    if name not in envs:
        raise ConfigError(f"unknown environment '{name}'")
    return envs[name]


def list_environments() -> dict:
    return load_config().get("environments", {})


def set_active(name: str) -> None:
    config = load_config()
    if name not in config.get("environments", {}):
        raise ConfigError(f"unknown environment '{name}'")
    config["active"] = name
    save_config(config)


def get_active() -> Optional[str]:
    return load_config().get("active")


def remove_environment(name: str) -> None:
    config = load_config()
    if name not in config.get("environments", {}):
        raise ConfigError(f"unknown environment '{name}'")
    del config["environments"][name]
    if config.get("active") == name:
        config["active"] = None
    save_config(config)
