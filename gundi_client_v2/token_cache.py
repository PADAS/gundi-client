"""Shared OAuth token cache for GundiClient.

A process-wide memory layer is always on; one optional durable backend (Redis
or a directory of files) sits behind it so replicas and restarts reuse a token
for as long as it is valid. See docs/superpowers/specs/2026-09-08-token-cache-design.md.
"""

import asyncio
import hashlib
import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Protocol, Tuple
from urllib.parse import urlparse

from gundi_core.schemas import OAuthToken

from .errors import TokenCacheConfigError

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
        if not isinstance(data, dict):
            return None
        access_token = data.get("access_token")
        # Every field is attacker-adjacent (whoever can write the backend can write
        # these): a non-string would reach OAuthToken as a ValidationError inside an
        # API call, and CR/LF/NUL in an access token would be smuggled into the
        # Authorization header the client builds from it.
        if not isinstance(access_token, str) or not access_token:
            return None
        if any(c in access_token for c in ("\r", "\n", "\x00")):
            return None
        optional = {}
        for field, default in (("refresh_token", ""), ("token_type", "Bearer")):
            value = data.get(field)
            if value is None:
                value = default
            elif not isinstance(value, str):
                return None
            optional[field] = value or default
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
        return cls(access_token=access_token, **optional, **stamps)


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
        # key -> (the loop the lock is bound to, the lock). An asyncio.Lock binds
        # to the loop that first contends it, so a process that runs more than one
        # event loop over its life (a worker calling asyncio.run per job) needs a
        # fresh lock per loop; reusing one raises "bound to a different event loop".
        self._locks: Dict[str, Tuple[asyncio.AbstractEventLoop, asyncio.Lock]] = {}

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
        loop = asyncio.get_running_loop()  # lock() is only called from a coroutine
        bound = self._locks.get(key)
        if bound is None or bound[0] is not loop or bound[0].is_closed():
            bound = (loop, asyncio.Lock())
            self._locks[key] = bound
        return bound[1]

    def clear(self) -> None:
        self._entries.clear()
        self._locks.clear()


_PROCESS_CACHE = MemoryTokenCache()


def clear_token_cache() -> None:
    """Empty the process-wide token layer and drop the per-URL backend memo.
    For tests, and for a long-running process that must drop every cached
    token (mirrors auth.clear_discovery_cache). Also resets the backend
    failure-streak flags, so a previously-failing backend is retried."""
    _PROCESS_CACHE.clear()
    _BACKENDS.clear()
    _FAILING_BACKENDS.clear()


class FileTokenCache:
    """One file per key under a private directory, for processes without Redis.

    Copies the CLI token store's conventions (gundi_client_v2/cli/token_store.py,
    config_store.write_private) rather than importing them, so the core library
    stays independent of the CLI package: 0700 directory, 0600 files, written to
    a temp name in the same directory and renamed into place so a reader never
    sees a partial file.
    """

    def __init__(self, directory: "Path | str") -> None:
        self.directory = Path(directory)

    def _path(self, key: str) -> Path:
        name = key[len(KEY_PREFIX) :] if key.startswith(KEY_PREFIX) else key
        return self.directory / f"{name}.json"

    async def get(self, key: str) -> "CachedToken | None":
        path = self._path(key)
        try:
            text = path.read_text()
        except FileNotFoundError:
            return None
        token = CachedToken.from_json(text)
        now = _now()
        if token is None or (not token.is_live(now) and not token.refresh_is_live(now)):
            self._unlink(path)
            return None
        return token

    async def set(self, key: str, token: CachedToken) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self._path(key)
        fd, tmp = tempfile.mkstemp(
            dir=str(self.directory), prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(
                    fd, 0o600
                )  # mkstemp already creates 0600; belt and suspenders
            with os.fdopen(fd, "w") as f:
                f.write(token.to_json())
            os.replace(tmp, path)
        except OSError:
            self._unlink(Path(tmp))
            raise

    async def delete(self, key: str) -> None:
        self._unlink(self._path(key))

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _import_redis():
    """Import redis lazily so `import gundi_client_v2` never requires it."""
    import redis  # noqa: WPS433 (optional dependency)
    import redis.asyncio  # noqa: F401

    return redis


class RedisTokenCache:
    """Redis-backed token cache shared by every process pointed at the same
    Redis. Values expire with the later of the two token expiries, so Redis
    prunes itself and never holds a token past its usefulness."""

    def __init__(
        self, url: "str | None" = None, client=None, *, socket_timeout: float = 1.0
    ) -> None:
        if (url is None) == (client is None):
            raise TokenCacheConfigError(
                "RedisTokenCache takes exactly one of url= or client="
            )
        if client is not None:
            self._client = client
            return
        try:
            redis = _import_redis()
        except ImportError as e:
            raise TokenCacheConfigError(
                "GUNDI_TOKEN_CACHE_URL points at Redis but the redis package is not "
                "installed; install gundi-client-v2[redis]."
            ) from e
        # A hung Redis must not stall an API call: every operation is bounded.
        self._client = redis.asyncio.Redis.from_url(
            url,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_timeout,
            decode_responses=True,
        )

    async def get(self, key: str) -> "CachedToken | None":
        raw = await self._client.get(key)
        if raw is None:
            return None
        token = CachedToken.from_json(raw)
        if token is None:
            await self._client.delete(key)
        return token

    async def set(self, key: str, token: CachedToken) -> None:
        latest = max(token.expires_at, token.refresh_expires_at)
        ttl = math.ceil((latest - _now()).total_seconds())
        if ttl <= 0:
            return
        await self._client.set(key, token.to_json(), ex=ttl)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)


# One backend object per URL per process: every GundiClient built from the same
# URL shares one Redis connection pool and one failure-streak flag.
_BACKENDS: Dict[str, "TokenCache"] = {}


def token_cache_from_url(url: "str | None") -> "TokenCache | None":
    """Build (once per process) the backend a GUNDI_TOKEN_CACHE_URL names;
    None means memory only."""
    if not url:
        return None
    cached = _BACKENDS.get(url)
    if cached is not None:
        return cached
    parsed = urlparse(url)
    if parsed.scheme in ("redis", "rediss"):
        backend = RedisTokenCache(url=url)
    elif parsed.scheme == "file":
        if not parsed.path:
            raise TokenCacheConfigError(
                "file:// token cache URL needs an absolute directory path"
            )
        backend = FileTokenCache(Path(parsed.path))
    else:
        raise TokenCacheConfigError(
            f"Unsupported token cache URL scheme {parsed.scheme!r}; use redis://, rediss:// or file:///dir"
        )
    _BACKENDS[url] = backend
    return backend


# Backends (by id) currently in a failure streak; shared by every TokenStore so
# an outage logs once per backend, not once per client built during it.
_FAILING_BACKENDS: set = set()


class TokenStore:
    """Memory layer in front of one optional backend.

    The cache never raises into an API call: a failing backend is logged at
    warning level once per failure streak (the flag resets on the next
    success) and treated as a miss or a skipped write. The log line names the
    backend class and the exception class, never a key or a token.
    """

    def __init__(
        self, backend: "TokenCache | None", memory: "MemoryTokenCache | None" = None
    ) -> None:
        self._backend = backend
        self._memory = memory if memory is not None else _PROCESS_CACHE

    def lock(self, key: str) -> asyncio.Lock:
        return self._memory.lock(key)

    async def get(self, key: str) -> "CachedToken | None":
        token = await self._memory.get(key)
        if token is not None or self._backend is None:
            return token
        token = await self._guarded("get", self._backend.get(key))
        if token is not None:
            await self._memory.set(key, token)
        return token

    async def set(self, key: str, token: CachedToken) -> None:
        await self._memory.set(key, token)
        if self._backend is not None:
            await self._guarded("set", self._backend.set(key, token))

    async def delete(self, key: str) -> None:
        await self._memory.delete(key)
        if self._backend is not None:
            await self._guarded("delete", self._backend.delete(key))

    async def _guarded(self, op: str, awaitable):
        marker = id(self._backend)
        try:
            result = await awaitable
        except Exception as e:  # any backend failure degrades to memory-only
            if marker not in _FAILING_BACKENDS:
                logger.warning(
                    "Token cache backend %s failed on %s (%s); running on the in-memory "
                    "layer until it recovers.",
                    type(self._backend).__name__,
                    op,
                    type(e).__name__,
                )
            _FAILING_BACKENDS.add(marker)
            return None
        _FAILING_BACKENDS.discard(marker)
        return result
