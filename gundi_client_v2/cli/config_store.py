"""Persistent CLI configuration: named environments stored under XDG config.

Stores only non-secret connection config in ``config.json``. Secrets are never
written here (see token_store for cached tokens). All files are user-private.
"""

import json
import os
import tempfile
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


def write_private(path: Path, text: str) -> None:
    """Atomically write ``text`` to a user-private (0600) file.

    Writes to a 0600 temp file in the same directory, then ``os.replace()`` s it
    into place — an atomic swap on POSIX. A crash mid-write leaves the previous
    good file intact (never a truncated/partial config or token), and the file
    is never briefly world-readable (``mkstemp`` creates it 0600).
    """
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        os.fchmod(fd, 0o600)  # mkstemp is already 0600; belt and suspenders
        with os.fdopen(fd, "w") as f:  # buffered writer handles partial writes
            f.write(text)
        os.replace(tmp, path)  # atomic rename over the destination
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def validate_env_name(name: str) -> None:
    """Reject environment names unsafe as a filename (path traversal, etc.).

    Names key both ``config.json`` and per-environment token filenames, so a
    name containing a path separator or ``..`` could escape the config dir.
    """
    if not name or name in (".", "..") or "/" in name or "\\" in name or "\x00" in name:
        raise ConfigError(f"invalid environment name: {name!r}")


def load_config() -> dict:
    path = config_file()
    if not path.exists():
        return {"active": None, "environments": {}}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigError(f"could not read config at {path}: {exc}")
    if not isinstance(data, dict):
        raise ConfigError(f"config at {path} is not a JSON object")
    active = data.get("active")
    if active is not None and not isinstance(active, str):
        raise ConfigError(f"config at {path}: 'active' must be a string or null")
    if not isinstance(data.get("environments", {}), dict):
        raise ConfigError(f"config at {path}: 'environments' must be an object")
    return data


def save_config(config: dict) -> None:
    ensure_dir(config_dir())
    write_private(config_file(), json.dumps(config, indent=2))


def add_environment(name: str, env: dict) -> None:
    validate_env_name(name)
    config = load_config()
    config.setdefault("environments", {})[name] = env
    save_config(config)


def get_environment(name: str) -> dict:
    envs = load_config().get("environments", {})
    if name not in envs:
        raise ConfigError(f"unknown environment '{name}'")
    return envs[name]


def get_environments() -> dict:
    """Return the mapping of environment name -> config dict."""
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
