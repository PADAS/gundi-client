"""Per-environment OAuth token cache.

Persists tokens derived from a login so subsequent CLI invocations reuse them
instead of re-authenticating. One file per environment under
``<config>/tokens/<env>.json`` (0600). Secrets are never stored here.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from gundi_core.schemas import OAuthToken

from . import config_store


def token_file(env_name: str) -> Path:
    return config_store.tokens_dir() / f"{env_name}.json"


def save_token(
    env_name: str, token: OAuthToken, expires_at: datetime, refresh_expires_at: datetime
) -> None:
    config_store.ensure_dir(config_store.tokens_dir())
    payload = {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "token_type": token.token_type,
        "expires_at": expires_at.isoformat(),
        "refresh_expires_at": refresh_expires_at.isoformat(),
    }
    path = token_file(env_name)
    path.write_text(json.dumps(payload, indent=2))
    os.chmod(path, 0o600)


def load_token(env_name: str) -> Optional[dict]:
    path = token_file(env_name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None  # corrupt cache == miss; caller falls back to re-auth


def delete_token(env_name: str) -> bool:
    path = token_file(env_name)
    if path.exists():
        path.unlink()
        return True
    return False


def apply_to_client(client, data: dict) -> None:
    """Restore a cached token onto a GundiClient so it skips re-authentication.

    Sets ``cached_token`` plus the two absolute expiry timestamps directly, so
    the client treats the token as live until it actually expires.
    """
    client.cached_token = OAuthToken(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", ""),
        token_type=data.get("token_type", "Bearer"),
        expires_in=0,
        refresh_expires_in=0,
    )
    client.cached_token_expires_at = datetime.fromisoformat(data["expires_at"])
    client.cached_token_refresh_expires_at = datetime.fromisoformat(
        data["refresh_expires_at"]
    )
