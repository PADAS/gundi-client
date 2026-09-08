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
import stat
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Protocol
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

    ``username`` is always part of the material: a CLI profile client carries a
    username and a restored token but no password, so several such clients under
    one client id would otherwise share one entry and adopt each other's tokens.
    ``secret`` is meant for a high-entropy client secret,
    so a rotated secret never reuses a token minted under the old one; callers
    must NOT pass a human password here — hashed next to guessable material it
    would make every key name an offline password verifier. ``token_url`` must
    be the resolved endpoint (after OIDC discovery) so an issuer-configured
    client and a token-URL-configured one share.
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
    ``refresh_expires_in`` are not stored because they are relative to a moment
    the reader does not know. ``to_oauth_token`` recomputes them on read.
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

    def to_oauth_token(self, now: "datetime | None" = None) -> OAuthToken:
        """The OAuthToken form, with the lifetimes left as of ``now``.

        Callers read ``expires_in`` to decide how long the token is good for,
        and ``refresh_access_token`` backfills a refresh response that omits
        ``refresh_expires_in`` from it, so both must be the remaining lifetime
        rather than the (unknown) value the IdP originally sent. Never negative.
        """
        now = now or _now()
        return OAuthToken(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            token_type=self.token_type,
            expires_in=max(0, int((self.expires_at - now).total_seconds())),
            refresh_expires_in=max(
                0, int((self.refresh_expires_at - now).total_seconds())
            ),
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
        # key -> {event loop -> Lock}. An asyncio.Lock binds to the loop that
        # first contends it, so each loop gets its own lock per key. Loops that
        # are closed or no longer running are pruned when the key is next
        # touched (a worker that builds a loop per job must not pin them all).
        # This dict is process-global and two threads may each run a loop, so
        # every mutation happens under _guard.
        self._locks: Dict[str, Dict[asyncio.AbstractEventLoop, asyncio.Lock]] = {}
        self._guard = threading.Lock()

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
        with self._guard:
            per_loop = self._locks.setdefault(key, {})
            for stale in [
                l for l in list(per_loop) if l.is_closed() or not l.is_running()
            ]:
                per_loop.pop(stale, None)
            lock = per_loop.get(loop)
            if lock is None:
                lock = per_loop[loop] = asyncio.Lock()
            return lock

    def clear(self) -> None:
        with self._guard:
            self._entries.clear()
            self._locks.clear()


_PROCESS_CACHE = MemoryTokenCache()


def clear_token_cache() -> None:
    """Empty the process-wide token layer and drop the per-URL backend memo.
    For tests, and for a long-running process that must drop every cached
    token (mirrors auth.clear_discovery_cache). Also resets the backend
    failure-streak flags, so a previously-failing backend is retried.

    Memoized Redis backends are dropped without closing their connection pools,
    so this is for tests and rare manual resets, not something to run on a
    timer: that would leak a pool per call."""
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
        self._checked_directory = False

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
        try:
            # No exist_ok: the chmod must apply only to a directory this call
            # created, never to one that appeared between a check and the mkdir.
            self.directory.mkdir(parents=True)
        except FileExistsError:
            # A pre-existing directory is the operator's, not the cache's, to
            # re-mode (file:///tmp as root would strip the sticky bit from /tmp).
            # Warn once if it is looser than 0700; the files stay 0600 either way.
            if not self._checked_directory:
                mode = stat.S_IMODE(os.stat(self.directory).st_mode)
                self._checked_directory = True  # only after the stat succeeded
                if mode & 0o077:
                    logger.warning(
                        "Token cache directory permissions are wider than 0700; the "
                        "cache files stay private, but the directory should be dedicated "
                        "to this cache and owner-only."
                    )
        else:
            os.chmod(self.directory, 0o700)
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
        # file://mydir/sub parses as host "mydir", path "/sub": the tokens would go
        # to the wrong directory without a word. Only file:///dir (or the explicit
        # file://localhost/dir) names a local absolute path.
        if parsed.netloc not in ("", "localhost"):
            raise TokenCacheConfigError(
                "file:// token cache URL must not have a host; "
                f"use file:///{parsed.netloc}{parsed.path}"
            )
        if not parsed.path.startswith("/"):
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

    async def reload(self, key: str) -> "CachedToken | None":
        """What every other client has written for ``key``: the backend's view
        when there is one (in-process siblings write there too), else memory's.
        For the forced-refresh path, where memory may hold the very token this
        instance was just rejected on and the question is whether someone has
        replaced it since."""
        if self._backend is None:
            return await self._memory.get(key)
        from_backend = await self._guarded("get", self._backend.get(key))
        if from_backend is not None:
            await self._memory.set(key, from_backend)
            return from_backend
        await self._memory.delete(key)
        return None

    async def get(self, key: str) -> "CachedToken | None":
        token = await self._memory.get(key)
        if self._backend is None or (token is not None and token.is_live(_now())):
            return token
        # Memory has nothing, or an entry whose access token is dead: another
        # replica may have refreshed it since, so ask the backend before falling
        # back on what memory holds (whose refresh token may still be usable).
        from_backend = await self._guarded("get", self._backend.get(key))
        if from_backend is not None and (token is None or from_backend.is_live(_now())):
            await self._memory.set(key, from_backend)
            return from_backend
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
