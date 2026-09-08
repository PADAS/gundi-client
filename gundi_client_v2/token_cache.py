"""Shared OAuth token cache for GundiClient.

A process-wide memory layer is always on; one optional durable backend (Redis
or a directory of files) sits behind it so replicas and restarts reuse a token
for as long as it is valid. See docs/superpowers/specs/2026-09-08-token-cache-design.md.
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Protocol

from gundi_core.schemas import OAuthToken

logger = logging.getLogger(__name__)

# The client's existing "no refresh token" sentinel.
NO_REFRESH = datetime.min.replace(tzinfo=timezone.utc)

KEY_PREFIX = "gundi-client:token:"


def token_cache_key(
    *,
    token_url: str,
    grant_type: str,
    client_id: "str | None",
    username: "str | None",
    audience: "str | None",
    scope: "str | None",
    secret: "str | None",
) -> str:
    """One key per set of credentials.

    The secret is part of the hashed material so a rotated secret never reuses
    a token minted under the old one, and two clients sharing an id with
    different secrets never collide. SHA-256 is one-way, so the key discloses
    nothing. ``token_url`` must be the resolved endpoint (after OIDC discovery)
    so an issuer-configured client and a token-URL-configured one share.
    """
    material = "\x1f".join(
        [
            token_url or "",
            grant_type or "",
            client_id or "",
            username or "",
            audience or "",
            scope or "",
            secret or "",
        ]
    )
    return KEY_PREFIX + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class CachedToken:
    """A token plus the absolute moments it stops being usable.

    The same payload the CLI token store writes; ``expires_in`` and
    ``refresh_expires_in`` are not kept because they are relative to a moment
    the reader does not know.
    """

    access_token: str
    refresh_token: str
    token_type: str
    expires_at: datetime
    refresh_expires_at: datetime

    def is_live(self, now: datetime) -> bool:
        return self.expires_at > now

    def refresh_is_live(self, now: datetime) -> bool:
        return bool(self.refresh_token) and self.refresh_expires_at > now

    def to_oauth_token(self) -> OAuthToken:
        return OAuthToken(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            token_type=self.token_type,
            expires_in=0,
            refresh_expires_in=0,
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "token_type": self.token_type,
                "expires_at": self.expires_at.isoformat(),
                "refresh_expires_at": self.refresh_expires_at.isoformat(),
            }
        )

    @classmethod
    def from_json(cls, text: str) -> "CachedToken | None":
        """Parse a serialized token; None for anything malformed (a miss)."""
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict) or not data.get("access_token"):
            return None
        stamps = {}
        for field in ("expires_at", "refresh_expires_at"):
            value = data.get(field)
            if not isinstance(value, str):
                return None
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return None
            stamps[field] = parsed
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token") or "",
            token_type=data.get("token_type") or "Bearer",
            **stamps,
        )


def _now() -> datetime:
    """The module's clock; tests replace it."""
    return datetime.now(tz=timezone.utc)


class TokenCache(Protocol):
    """A durable token store. Implementations may raise; TokenStore contains it."""

    async def get(self, key: str) -> "CachedToken | None": ...

    async def set(self, key: str, token: CachedToken) -> None: ...

    async def delete(self, key: str) -> None: ...


class MemoryTokenCache:
    """Process-wide in-memory layer.

    Entries whose access and refresh tokens have both expired are dropped on
    read. A per-key asyncio.Lock lets concurrent clients that miss at the same
    moment wait for one fetch instead of each making their own.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, CachedToken] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    async def get(self, key: str) -> "CachedToken | None":
        token = self._entries.get(key)
        if token is None:
            return None
        now = _now()
        if not token.is_live(now) and not token.refresh_is_live(now):
            del self._entries[key]
            return None
        return token

    async def set(self, key: str, token: CachedToken) -> None:
        self._entries[key] = token

    async def delete(self, key: str) -> None:
        self._entries.pop(key, None)

    def lock(self, key: str) -> asyncio.Lock:
        # setdefault is atomic enough: asyncio is single-threaded and there is
        # no await between the lookup and the insert.
        return self._locks.setdefault(key, asyncio.Lock())

    def clear(self) -> None:
        self._entries.clear()
        self._locks.clear()


_PROCESS_CACHE = MemoryTokenCache()


def clear_token_cache() -> None:
    """Empty the process-wide token layer. For tests, and for a long-running
    process that must drop every cached token (mirrors auth.clear_discovery_cache)."""
    _PROCESS_CACHE.clear()
