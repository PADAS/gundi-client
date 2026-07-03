"""Per-environment OAuth token cache.

Persists tokens derived from a login so subsequent CLI invocations reuse them
instead of re-authenticating. One file per environment under
``<config>/tokens/<env>.json`` (0600). Secrets are never stored here.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from gundi_core.schemas import OAuthToken

from . import config_store


def token_file(env_name: str) -> Path:
    tokens = config_store.tokens_dir()
    path = tokens / f"{env_name}.json"
    # Defense in depth: a name with a path separator or ``..`` must not escape
    # the tokens directory. (Names are also validated at `env add` time.)
    if path.resolve().parent != tokens.resolve():
        raise ValueError(f"invalid environment name: {env_name!r}")
    return path


def save_token(
    env_name: str, token: OAuthToken, expires_at: datetime, refresh_expires_at: datetime
) -> None:
    try:
        path = token_file(env_name)  # may raise ValueError for an unsafe name
    except ValueError as exc:
        raise config_store.ConfigError(f"invalid environment for token cache: {exc}")
    config_store.ensure_dir(config_store.tokens_dir())  # raises ConfigError on OSError
    payload = {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "token_type": token.token_type,
        "expires_at": expires_at.isoformat(),
        "refresh_expires_at": refresh_expires_at.isoformat(),
    }
    config_store.write_private(
        path, json.dumps(payload, indent=2)
    )  # ConfigError on OSError


def load_token(env_name: str) -> Optional[dict]:
    path = token_file(env_name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None  # corrupt cache == miss; caller falls back to re-auth
    if not _is_valid_token_data(data):
        return None  # malformed/incomplete cache == miss; re-auth instead of crashing
    return data


def _is_valid_token_data(data) -> bool:
    """Check a cached token has the fields ``apply_to_client`` requires.

    Guards against a valid-JSON-but-malformed cache (missing keys or a
    non-ISO timestamp) that would otherwise raise from ``apply_to_client``.
    """
    if not isinstance(data, dict) or not data.get("access_token"):
        return False
    for key in ("expires_at", "refresh_expires_at"):
        value = data.get(key)
        if not isinstance(value, str):
            return False
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return False
        # Must be tz-aware; a naive timestamp would crash later comparisons
        # against timezone-aware "now" (e.g. in `auth status`).
        if parsed.tzinfo is None:
            return False
    return True


def delete_token(env_name: str) -> bool:
    """Delete the cached token; return True iff a file was actually removed.

    Never raises: attempting the unlink directly (rather than exists()-then-unlink)
    avoids a TOCTOU race, and any OSError — a missing file (the common case) or a
    filesystem error — is reported as False so `logout`/`env remove` don't emit a
    traceback.
    """
    try:
        token_file(env_name).unlink()
        return True
    except OSError:
        return False


def apply_to_client(client, data: dict) -> None:
    """Restore a cached token onto a GundiClient so it skips re-authentication.

    Sets ``cached_token`` plus the two absolute expiry timestamps directly, so
    the client treats the token as live until it actually expires.
    """
    client.cached_token = OAuthToken(
        access_token=data["access_token"],
        # `or` (not .get default) so an explicit JSON null coerces to the default.
        refresh_token=data.get("refresh_token") or "",
        token_type=data.get("token_type") or "Bearer",
        expires_in=0,
        refresh_expires_in=0,
    )
    client.cached_token_expires_at = datetime.fromisoformat(data["expires_at"])
    client.cached_token_refresh_expires_at = datetime.fromisoformat(
        data["refresh_expires_at"]
    )
