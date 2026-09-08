# Shared OAuth Token Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every `GundiClient` in a process, and every process sharing a Redis, reuse one Keycloak token per set of credentials for as long as it is valid.

**Architecture:** A new `gundi_client_v2/token_cache.py` module defines a `CachedToken` record, a `TokenCache` protocol with memory, Redis and file implementations, and a `TokenStore` coordinator that keeps a process-wide memory layer in front of one optional backend. `GundiClient.get_access_token` consults the store before authenticating and writes back whatever it fetches; a forced refresh evicts the shared entry first. The backend is chosen by `GUNDI_TOKEN_CACHE_URL` / `token_cache_url=` or injected via `token_cache=`. Part B wires the action-runner template to it through one factory and its existing Redis settings.

**Tech Stack:** Python 3.10+, httpx, pydantic 1.x (`gundi_core.schemas.OAuthToken`), `redis.asyncio` (optional extra), pytest + pytest-asyncio + respx + fakeredis, uv.

**Spec:** `docs/superpowers/specs/2026-09-08-token-cache-design.md`

## Global Constraints

- Library release is **3.7.0** (`gundi_client_v2/__init__.py` `__version__`). Part B depends on it being published.
- Python `>=3.10`; pydantic `>=1.10,<2`; httpx `>=0.28,<1`; keep `from __future__` out (the codebase uses `X | None` syntax directly, which 3.10 supports).
- The `redis` package is an **optional extra** (`pip install gundi-client-v2[redis]`, pin `redis>=5,<9`). `import redis` must never happen at `import gundi_client_v2`.
- The core library must not import from `gundi_client_v2.cli` (the file-writing helper is copied, not imported).
- The cache never raises into an API call; configuration errors raise `TokenCacheConfigError` (a `GundiClientError`) at construction.
- Log lines never contain a key or a token; the secret enters the key only inside a SHA-256.
- Expiry buffer stays the existing `GundiClient._expiry_with_buffer` (15 s, capped at half the lifetime).
- Redis key prefix is exactly `gundi-client:token:`; Redis `SET` uses `EX` = seconds until the later of the two expiries.
- File backend: directory 0700, files 0600, temp-file-plus-`os.replace` writes.
- Formatting: `uv run black --check .` must pass (CI runs it).
- Run tests from the worktree with `uv run pytest -q` (baseline: 224 passed).
- Commit messages: conventional prefix (`feat:`, `test:`, `docs:`, `chore:`), and end with
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01XiRFpnqiEX9VeEJk5DD8ck` on their own lines.

## Repository layout for this work

- Library repo: `/Users/chrisdo/padas/gundi-client`. Work in the worktree `.worktrees/token-cache` on branch `cd/token-cache` (based on `origin/v2`, the 3.x line; `origin/main` is the old 2.x line, do not base on it). The spec is already committed there.
- Template repo (Part B): `/Users/chrisdo/padas/gundi-integration-action-runner`. Create a worktree `.worktrees/token-cache -b cd/token-cache origin/main` there; tests run with `../../.venv/bin/python -m pytest` from inside the worktree.

## File structure (Part A, library)

| File | Responsibility |
|---|---|
| `gundi_client_v2/token_cache.py` (new) | `CachedToken`, serialization, `token_cache_key`, `TokenCache` protocol, `MemoryTokenCache`, `FileTokenCache`, `RedisTokenCache`, `token_cache_from_url`, `TokenStore`, `clear_token_cache` |
| `gundi_client_v2/errors.py` | add `TokenCacheConfigError` |
| `gundi_client_v2/settings.py` | add `GUNDI_TOKEN_CACHE_URL` |
| `gundi_client_v2/client.py` | `GundiClient` constructor kwargs, `_token_store`, `get_access_token` rewritten around the store, `_fetch_token`, `_adopt`, `_store_token` kept as a compatibility wrapper |
| `gundi_client_v2/__init__.py` | version 3.7.0, export `token_cache` names |
| `pyproject.toml` | `redis` extra; `fakeredis` dev dependency |
| `tests/conftest.py` | autouse fixture clearing the process token cache |
| `tests/client/test_token_cache.py` (new) | unit tests for the module |
| `tests/client/test_token_cache_client.py` (new) | `GundiClient` behaviour with the cache |
| `docs/authentication/token-cache.md` (new), `mkdocs.yml`, `README.md`, `docs/authentication/refresh-and-errors.md`, `docs/api-reference/auth.md` | documentation |

---

## Part A — gundi-client-v2

### Task 1: `CachedToken` record and JSON round-trip

**Files:**
- Create: `gundi_client_v2/token_cache.py`
- Test: `tests/client/test_token_cache.py`

**Interfaces:**
- Produces:
  - `CachedToken(access_token: str, refresh_token: str, token_type: str, expires_at: datetime, refresh_expires_at: datetime)` frozen dataclass
  - `CachedToken.is_live(now: datetime) -> bool`, `CachedToken.refresh_is_live(now: datetime) -> bool`, `CachedToken.to_oauth_token() -> OAuthToken`
  - `CachedToken.to_json() -> str`, `CachedToken.from_json(text: str) -> CachedToken | None` (None on anything malformed)
  - `NO_REFRESH: datetime` = `datetime.min.replace(tzinfo=timezone.utc)` (the "no refresh token" sentinel the client already uses)

- [ ] **Step 1: Write the failing tests**

```python
# tests/client/test_token_cache.py
import json
from datetime import datetime, timedelta, timezone

import pytest

from gundi_client_v2.token_cache import NO_REFRESH, CachedToken

NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)


def _token(**overrides) -> CachedToken:
    fields = dict(
        access_token="access-1",
        refresh_token="refresh-1",
        token_type="Bearer",
        expires_at=NOW + timedelta(hours=1),
        refresh_expires_at=NOW + timedelta(hours=10),
    )
    fields.update(overrides)
    return CachedToken(**fields)


def test_liveness_uses_absolute_timestamps():
    token = _token()
    assert token.is_live(NOW)
    assert not token.is_live(NOW + timedelta(hours=2))
    assert token.refresh_is_live(NOW + timedelta(hours=2))
    assert not token.refresh_is_live(NOW + timedelta(hours=11))


def test_no_refresh_token_is_never_refresh_live():
    token = _token(refresh_token="", refresh_expires_at=NO_REFRESH)
    assert not token.refresh_is_live(NOW)


def test_to_oauth_token_zeroes_relative_lifetimes():
    oauth = _token().to_oauth_token()
    assert oauth.access_token == "access-1"
    assert oauth.refresh_token == "refresh-1"
    assert oauth.token_type == "Bearer"
    assert oauth.expires_in == 0
    assert oauth.refresh_expires_in == 0


def test_json_round_trip():
    token = _token()
    restored = CachedToken.from_json(token.to_json())
    assert restored == token
    payload = json.loads(token.to_json())
    assert set(payload) == {
        "access_token", "refresh_token", "token_type", "expires_at", "refresh_expires_at",
    }


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        json.dumps({"access_token": ""}),
        json.dumps({"access_token": "a", "expires_at": "yesterday", "refresh_expires_at": "2026-01-01T00:00:00+00:00"}),
        json.dumps({"access_token": "a", "expires_at": "2026-01-01T00:00:00", "refresh_expires_at": "2026-01-01T00:00:00+00:00"}),  # naive timestamp
    ],
)
def test_from_json_returns_none_for_malformed_input(text):
    assert CachedToken.from_json(text) is None


def test_from_json_defaults_optional_fields():
    text = json.dumps({
        "access_token": "a",
        "expires_at": "2026-01-01T00:00:00+00:00",
        "refresh_expires_at": "2026-01-01T00:00:00+00:00",
    })
    token = CachedToken.from_json(text)
    assert token.refresh_token == ""
    assert token.token_type == "Bearer"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/client/test_token_cache.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'gundi_client_v2.token_cache'`

- [ ] **Step 3: Write the minimal implementation**

```python
# gundi_client_v2/token_cache.py
"""Shared OAuth token cache for GundiClient.

A process-wide memory layer is always on; one optional durable backend (Redis
or a directory of files) sits behind it so replicas and restarts reuse a token
for as long as it is valid. See docs/superpowers/specs/2026-09-08-token-cache-design.md.
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from gundi_core.schemas import OAuthToken

logger = logging.getLogger(__name__)

# The client's existing "no refresh token" sentinel.
NO_REFRESH = datetime.min.replace(tzinfo=timezone.utc)


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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/client/test_token_cache.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add gundi_client_v2/token_cache.py tests/client/test_token_cache.py
git commit -m "feat(token-cache): CachedToken record with JSON round-trip"
```

---

### Task 2: Cache key derivation

**Files:**
- Modify: `gundi_client_v2/token_cache.py`
- Test: `tests/client/test_token_cache.py`

**Interfaces:**
- Produces: `token_cache_key(*, token_url: str, grant_type: str, client_id: str | None, username: str | None, audience: str | None, scope: str | None, secret: str | None) -> str` returning `"gundi-client:token:" + 32 hex chars`; `KEY_PREFIX = "gundi-client:token:"`

- [ ] **Step 1: Write the failing tests**

Append to `tests/client/test_token_cache.py`:

```python
from gundi_client_v2.token_cache import KEY_PREFIX, token_cache_key

_KEY_ARGS = dict(
    token_url="https://auth.example/realms/dev/protocol/openid-connect/token",
    grant_type="client_credentials",
    client_id="runner",
    username=None,
    audience="portal",
    scope="openid",
    secret="s3cret",
)


def test_key_is_prefixed_hex_and_stable():
    key = token_cache_key(**_KEY_ARGS)
    assert key.startswith(KEY_PREFIX)
    digest = key[len(KEY_PREFIX):]
    assert len(digest) == 32 and int(digest, 16) >= 0
    assert key == token_cache_key(**_KEY_ARGS)


def test_key_never_contains_the_secret_or_client_id():
    key = token_cache_key(**_KEY_ARGS)
    assert "s3cret" not in key
    assert "runner" not in key


@pytest.mark.parametrize(
    "change",
    [
        {"secret": "rotated"},
        {"client_id": "other"},
        {"token_url": "https://auth.example/realms/prod/protocol/openid-connect/token"},
        {"grant_type": "password", "username": "alice"},
        {"audience": "other-portal"},
        {"scope": "openid email"},
    ],
)
def test_key_changes_when_any_credential_component_changes(change):
    assert token_cache_key(**{**_KEY_ARGS, **change}) != token_cache_key(**_KEY_ARGS)


def test_key_treats_none_and_empty_alike():
    assert token_cache_key(**{**_KEY_ARGS, "audience": None}) == token_cache_key(
        **{**_KEY_ARGS, "audience": ""}
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/client/test_token_cache.py -q -k key`
Expected: FAIL with `ImportError: cannot import name 'KEY_PREFIX'`

- [ ] **Step 3: Write the minimal implementation**

Add to `gundi_client_v2/token_cache.py` (after the imports, add `import hashlib`):

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/client/test_token_cache.py -q`
Expected: all passed (7 + 9)

- [ ] **Step 5: Commit**

```bash
git add gundi_client_v2/token_cache.py tests/client/test_token_cache.py
git commit -m "feat(token-cache): credential-derived cache key"
```

---

### Task 3: `TokenCache` protocol, `MemoryTokenCache` and `clear_token_cache`

**Files:**
- Modify: `gundi_client_v2/token_cache.py`
- Modify: `tests/conftest.py`
- Test: `tests/client/test_token_cache.py`

**Interfaces:**
- Produces:
  - `class TokenCache(Protocol)`: `async get(key) -> CachedToken | None`, `async set(key, token: CachedToken) -> None`, `async delete(key) -> None`
  - `class MemoryTokenCache`: implements `TokenCache` over a dict it owns; `get` drops and returns None for an entry whose access **and** refresh are both expired; `lock(key) -> asyncio.Lock` per key; `clear()`
  - Module-level `_PROCESS_CACHE = MemoryTokenCache()` and `clear_token_cache() -> None`
  - `_now() -> datetime` module function (UTC), the single clock the module and its tests use

- [ ] **Step 1: Write the failing tests**

Append to `tests/client/test_token_cache.py`:

```python
import asyncio

from gundi_client_v2 import token_cache as tc
from gundi_client_v2.token_cache import MemoryTokenCache, clear_token_cache


@pytest.fixture
def clock(monkeypatch):
    state = {"now": NOW}
    monkeypatch.setattr(tc, "_now", lambda: state["now"])
    return state


@pytest.mark.asyncio
async def test_memory_cache_round_trip(clock):
    cache = MemoryTokenCache()
    assert await cache.get("k") is None
    await cache.set("k", _token())
    assert await cache.get("k") == _token()
    await cache.delete("k")
    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_memory_cache_keeps_an_entry_whose_refresh_token_is_still_live(clock):
    cache = MemoryTokenCache()
    await cache.set("k", _token())
    clock["now"] = NOW + timedelta(hours=2)  # access expired, refresh live
    assert await cache.get("k") == _token()


@pytest.mark.asyncio
async def test_memory_cache_drops_an_entry_whose_tokens_have_both_expired(clock):
    cache = MemoryTokenCache()
    await cache.set("k", _token())
    clock["now"] = NOW + timedelta(hours=11)
    assert await cache.get("k") is None
    assert "k" not in cache._entries


def test_memory_cache_lock_is_per_key():
    cache = MemoryTokenCache()
    assert cache.lock("a") is cache.lock("a")
    assert cache.lock("a") is not cache.lock("b")
    assert isinstance(cache.lock("a"), asyncio.Lock)


@pytest.mark.asyncio
async def test_clear_token_cache_empties_the_process_layer():
    await tc._PROCESS_CACHE.set("k", _token())
    clear_token_cache()
    assert await tc._PROCESS_CACHE.get("k") is None
    assert tc._PROCESS_CACHE._locks == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/client/test_token_cache.py -q -k "memory or clear"`
Expected: FAIL with `ImportError: cannot import name 'MemoryTokenCache'`

- [ ] **Step 3: Write the minimal implementation**

Add to `gundi_client_v2/token_cache.py` (add `import asyncio` and `from typing import Dict, Protocol` to the imports):

```python
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
    process that must drop every cached token (mirrors auth.clear_discovery_cache).
    Task 5 extends this to also clear the per-URL backend memo and Task 6 the
    failure-streak flags; the final body is:

        _PROCESS_CACHE.clear()
        _BACKENDS.clear()
        _FAILING_BACKENDS.clear()

    Define ``_BACKENDS`` and ``_FAILING_BACKENDS`` as empty containers now if you
    want the final body in place from this task.
    """
    _PROCESS_CACHE.clear()
```

- [ ] **Step 4: Add the autouse fixture to `tests/conftest.py`**

After `_clear_oidc_discovery_cache`, add:

```python
@pytest.fixture(autouse=True)
def _clear_process_token_cache():
    """Keep the process-wide token cache test-isolated."""
    from gundi_client_v2 import token_cache as _token_cache

    _token_cache.clear_token_cache()
    yield
    _token_cache.clear_token_cache()
```

- [ ] **Step 5: Run the full suite to verify it passes**

Run: `uv run pytest -q`
Expected: all passed (224 + 21)

- [ ] **Step 6: Commit**

```bash
git add gundi_client_v2/token_cache.py tests/client/test_token_cache.py tests/conftest.py
git commit -m "feat(token-cache): TokenCache protocol, process-wide memory layer, clear_token_cache"
```

---

### Task 4: `FileTokenCache`

**Files:**
- Modify: `gundi_client_v2/token_cache.py`
- Test: `tests/client/test_token_cache.py`

**Interfaces:**
- Produces: `class FileTokenCache(directory: Path | str)`: implements `TokenCache`; one file `<directory>/<key with the prefix stripped>.json`; directory created 0700 on first write; files 0600, written to a temp name then `os.replace`d; `get` deletes and returns None for an entry whose tokens have both expired or that is malformed. Raises `OSError` from `set`/`delete` on filesystem failure (the coordinator in Task 6 contains it).

- [ ] **Step 1: Write the failing tests**

Append to `tests/client/test_token_cache.py`:

```python
import os
import stat
from pathlib import Path

from gundi_client_v2.token_cache import FileTokenCache


@pytest.mark.asyncio
async def test_file_cache_round_trip_and_layout(tmp_path, clock):
    cache = FileTokenCache(tmp_path / "tokens")
    key = KEY_PREFIX + "ab" * 16
    assert await cache.get(key) is None
    await cache.set(key, _token())
    assert await cache.get(key) == _token()
    files = list((tmp_path / "tokens").iterdir())
    assert [f.name for f in files] == ["ab" * 16 + ".json"]
    await cache.delete(key)
    assert await cache.get(key) is None
    await cache.delete(key)  # deleting a missing entry is not an error


@pytest.mark.asyncio
async def test_file_cache_permissions(tmp_path, clock):
    cache = FileTokenCache(tmp_path / "tokens")
    key = KEY_PREFIX + "cd" * 16
    await cache.set(key, _token())
    assert stat.S_IMODE(os.stat(tmp_path / "tokens").st_mode) == 0o700
    assert stat.S_IMODE(os.stat(tmp_path / "tokens" / ("cd" * 16 + ".json")).st_mode) == 0o600


@pytest.mark.asyncio
async def test_file_cache_write_is_atomic_and_leaves_no_temp_file(tmp_path, clock, monkeypatch):
    cache = FileTokenCache(tmp_path / "tokens")
    key = KEY_PREFIX + "ef" * 16
    await cache.set(key, _token(access_token="first"))

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError):
        await cache.set(key, _token(access_token="second"))
    monkeypatch.undo()
    assert (await cache.get(key)).access_token == "first"
    assert [f.name for f in (tmp_path / "tokens").iterdir()] == ["ef" * 16 + ".json"]


@pytest.mark.asyncio
async def test_file_cache_treats_corrupt_and_expired_files_as_misses_and_removes_them(tmp_path, clock):
    cache = FileTokenCache(tmp_path / "tokens")
    key = KEY_PREFIX + "01" * 16
    await cache.set(key, _token())
    path = tmp_path / "tokens" / ("01" * 16 + ".json")
    path.write_text("{not json")
    assert await cache.get(key) is None
    assert not path.exists()

    await cache.set(key, _token())
    clock["now"] = NOW + timedelta(hours=11)
    assert await cache.get(key) is None
    assert not path.exists()


def test_file_cache_accepts_a_string_directory(tmp_path):
    cache = FileTokenCache(str(tmp_path / "tokens"))
    assert cache.directory == tmp_path / "tokens"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/client/test_token_cache.py -q -k file`
Expected: FAIL with `ImportError: cannot import name 'FileTokenCache'`

- [ ] **Step 3: Write the minimal implementation**

Add to `gundi_client_v2/token_cache.py` (add `import os`, `import tempfile`, `from pathlib import Path` to the imports):

```python
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
        name = key[len(KEY_PREFIX):] if key.startswith(KEY_PREFIX) else key
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
        fd, tmp = tempfile.mkstemp(dir=str(self.directory), prefix=f".{path.name}.", suffix=".tmp")
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)  # mkstemp already creates 0600; belt and suspenders
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/client/test_token_cache.py -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add gundi_client_v2/token_cache.py tests/client/test_token_cache.py
git commit -m "feat(token-cache): FileTokenCache with private, atomic files"
```

---

### Task 5: `RedisTokenCache`, the `redis` extra, `TokenCacheConfigError`, `token_cache_from_url`

**Files:**
- Modify: `gundi_client_v2/token_cache.py`
- Modify: `gundi_client_v2/errors.py`
- Modify: `pyproject.toml`
- Test: `tests/client/test_token_cache.py`

**Interfaces:**
- Produces:
  - `errors.TokenCacheConfigError(GundiClientError)`
  - `class RedisTokenCache(url: str | None = None, client=None, *, socket_timeout: float = 1.0)`: implements `TokenCache`; exactly one of `url`/`client`; `set` uses `SET key value EX ttl` where `ttl = ceil(seconds until max(expires_at, refresh_expires_at))`, skipping the write when that is `<= 0`; `get` returns None and deletes on a malformed value; raises `TokenCacheConfigError` when built from a URL and `redis` is not importable
  - `token_cache_from_url(url: str | None) -> TokenCache | None`: `None`/`""` → None; `redis://`, `rediss://` → `RedisTokenCache(url=url)`; `file:///dir` → `FileTokenCache(Path)`; anything else → `TokenCacheConfigError`. **Memoized per URL for the process** (`_BACKENDS: dict[str, TokenCache]`), so every `GundiClient()` built from the same URL shares one backend object, one Redis connection pool, and one failure-streak flag. `clear_token_cache()` also empties the memo.

- [ ] **Step 1: Add the dependency declarations**

In `pyproject.toml`, under `[project.optional-dependencies]` add:

```toml
# Redis-backed token cache (RedisTokenCache / GUNDI_TOKEN_CACHE_URL=redis://...).
redis = [
    "redis>=5,<9",
]
```

and under `[dependency-groups] dev` add `"fakeredis>=2.20",` and `"redis>=5,<9",`. Then run `uv sync` and `uv lock` so `uv.lock` records them.

- [ ] **Step 2: Write the failing tests**

Append to `tests/client/test_token_cache.py`:

```python
import math

from fakeredis import FakeAsyncRedis

from gundi_client_v2.errors import GundiClientError, TokenCacheConfigError
from gundi_client_v2.token_cache import RedisTokenCache, token_cache_from_url


@pytest.fixture
def fake_redis():
    return FakeAsyncRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_redis_cache_round_trip(fake_redis, clock):
    cache = RedisTokenCache(client=fake_redis)
    key = KEY_PREFIX + "aa" * 16
    assert await cache.get(key) is None
    await cache.set(key, _token())
    assert await cache.get(key) == _token()
    assert await fake_redis.exists(key) == 1
    await cache.delete(key)
    assert await cache.get(key) is None


@pytest.mark.asyncio
async def test_redis_cache_sets_ttl_to_the_later_expiry(fake_redis, clock):
    cache = RedisTokenCache(client=fake_redis)
    key = KEY_PREFIX + "bb" * 16
    await cache.set(key, _token())  # refresh lives 10 h, access 1 h
    ttl = await fake_redis.ttl(key)
    assert 10 * 3600 - 2 <= ttl <= 10 * 3600


@pytest.mark.asyncio
async def test_redis_cache_skips_writing_an_already_expired_token(fake_redis, clock):
    cache = RedisTokenCache(client=fake_redis)
    key = KEY_PREFIX + "cc" * 16
    clock["now"] = NOW + timedelta(hours=11)
    await cache.set(key, _token())
    assert await fake_redis.exists(key) == 0


@pytest.mark.asyncio
async def test_redis_cache_treats_a_corrupt_value_as_a_miss_and_deletes_it(fake_redis, clock):
    cache = RedisTokenCache(client=fake_redis)
    key = KEY_PREFIX + "dd" * 16
    await fake_redis.set(key, "{oops")
    assert await cache.get(key) is None
    assert await fake_redis.exists(key) == 0


def test_redis_cache_requires_exactly_one_of_url_or_client(fake_redis):
    with pytest.raises(TokenCacheConfigError):
        RedisTokenCache()
    with pytest.raises(TokenCacheConfigError):
        RedisTokenCache(url="redis://localhost/2", client=fake_redis)


def test_redis_cache_without_the_redis_package_fails_at_construction(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_redis(name, *args, **kwargs):
        if name == "redis" or name.startswith("redis."):
            raise ImportError("No module named 'redis'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_redis)
    with pytest.raises(TokenCacheConfigError, match=r"gundi-client-v2\[redis\]"):
        RedisTokenCache(url="redis://localhost:6379/2")


def test_token_cache_config_error_is_a_client_error():
    assert issubclass(TokenCacheConfigError, GundiClientError)


def test_token_cache_from_url_selects_the_backend(tmp_path):
    assert token_cache_from_url(None) is None
    assert token_cache_from_url("") is None
    assert isinstance(token_cache_from_url("redis://localhost:6379/2"), RedisTokenCache)
    assert isinstance(token_cache_from_url("rediss://localhost:6380/2"), RedisTokenCache)
    file_cache = token_cache_from_url(f"file://{tmp_path}/tokens")
    assert isinstance(file_cache, FileTokenCache)
    assert file_cache.directory == tmp_path / "tokens"


@pytest.mark.parametrize("url", ["memcached://x", "http://x", "file://", "redis"])
def test_token_cache_from_url_rejects_unsupported_urls(url):
    with pytest.raises(TokenCacheConfigError):
        token_cache_from_url(url)


def test_token_cache_from_url_returns_one_backend_per_url_per_process(tmp_path):
    a = token_cache_from_url("redis://localhost:6379/2")
    b = token_cache_from_url("redis://localhost:6379/2")
    c = token_cache_from_url("redis://localhost:6379/3")
    assert a is b and a is not c
    f1 = token_cache_from_url(f"file://{tmp_path}")
    assert token_cache_from_url(f"file://{tmp_path}") is f1
    clear_token_cache()
    assert token_cache_from_url("redis://localhost:6379/2") is not a


def test_redis_url_uses_a_short_socket_timeout(monkeypatch):
    captured = {}

    class FakeRedisModule:
        class asyncio:
            class Redis:
                @staticmethod
                def from_url(url, **kwargs):
                    captured.update(kwargs, url=url)
                    return object()

    monkeypatch.setattr(tc, "_import_redis", lambda: FakeRedisModule)
    RedisTokenCache(url="redis://h:1/2")
    assert captured["url"] == "redis://h:1/2"
    assert captured["socket_timeout"] == 1.0
    assert captured["socket_connect_timeout"] == 1.0
    assert captured["decode_responses"] is True
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/client/test_token_cache.py -q -k "redis or config or from_url"`
Expected: FAIL with `ImportError: cannot import name 'TokenCacheConfigError'`

- [ ] **Step 4: Write the minimal implementation**

In `gundi_client_v2/errors.py`, after `AuthenticationError`:

```python
class TokenCacheConfigError(GundiClientError):
    """Raised at construction when the token-cache configuration is unusable:
    an unsupported GUNDI_TOKEN_CACHE_URL, or a redis:// URL without the
    ``redis`` package installed (``pip install gundi-client-v2[redis]``)."""
```

In `gundi_client_v2/token_cache.py` (add `import math` and `from urllib.parse import urlparse` to the imports, and `from .errors import TokenCacheConfigError`):

```python
def _import_redis():
    """Import redis lazily so `import gundi_client_v2` never requires it."""
    import redis  # noqa: WPS433 (optional dependency)
    import redis.asyncio  # noqa: F401

    return redis


class RedisTokenCache:
    """Redis-backed token cache shared by every process pointed at the same
    Redis. Values expire with the later of the two token expiries, so Redis
    prunes itself and never holds a token past its usefulness."""

    def __init__(self, url: "str | None" = None, client=None, *, socket_timeout: float = 1.0) -> None:
        if (url is None) == (client is None):
            raise TokenCacheConfigError("RedisTokenCache takes exactly one of url= or client=")
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
            raise TokenCacheConfigError("file:// token cache URL needs an absolute directory path")
        backend = FileTokenCache(Path(parsed.path))
    else:
        raise TokenCacheConfigError(
            f"Unsupported token cache URL scheme {parsed.scheme!r}; use redis://, rediss:// or file:///dir"
        )
    _BACKENDS[url] = backend
    return backend
```

Extend `clear_token_cache()` so it also runs `_BACKENDS.clear()`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/client/test_token_cache.py -q`
Expected: all passed

- [ ] **Step 6: Verify the optional import contract**

Run: `uv run python -c "import sys; import gundi_client_v2, gundi_client_v2.token_cache; assert 'redis' not in sys.modules, sys.modules.keys() & {'redis'}; print('redis not imported at module load')"`
Expected: `redis not imported at module load`

- [ ] **Step 7: Commit**

```bash
git add gundi_client_v2/token_cache.py gundi_client_v2/errors.py pyproject.toml uv.lock tests/client/test_token_cache.py
git commit -m "feat(token-cache): RedisTokenCache, redis extra, token_cache_from_url"
```

---

### Task 6: `TokenStore` coordinator with contained backend failures

**Files:**
- Modify: `gundi_client_v2/token_cache.py`
- Test: `tests/client/test_token_cache.py`

**Interfaces:**
- Produces: `class TokenStore(backend: TokenCache | None, memory: MemoryTokenCache = _PROCESS_CACHE)`:
  - `lock(key) -> asyncio.Lock` (the memory layer's)
  - `async get(key) -> CachedToken | None`: memory first; on a miss, the backend, whose hit is copied into memory
  - `async set(key, token)`: memory then backend
  - `async delete(key)`: memory then backend
  - Backend exceptions (any `Exception`) are logged at WARNING once per failure streak **per backend object** (a module-level `_FAILING_BACKENDS: set[int]` of `id(backend)`, so every `TokenStore` sharing a memoized backend shares the streak) and swallowed; the log line names the backend class and the exception class only

- [ ] **Step 1: Write the failing tests**

Append to `tests/client/test_token_cache.py`:

```python
import logging

from gundi_client_v2.token_cache import TokenStore


class _Flaky:
    """A TokenCache whose every call raises."""

    def __init__(self):
        self.calls = 0

    async def get(self, key):
        self.calls += 1
        raise ConnectionError("redis down")

    async def set(self, key, token):
        self.calls += 1
        raise ConnectionError("redis down")

    async def delete(self, key):
        self.calls += 1
        raise ConnectionError("redis down")


@pytest.mark.asyncio
async def test_store_reads_memory_before_the_backend(fake_redis, clock):
    backend = RedisTokenCache(client=fake_redis)
    store = TokenStore(backend, memory=MemoryTokenCache())
    await store.set("k", _token())
    await fake_redis.delete("k")  # backend lost it; memory still answers
    assert await store.get("k") == _token()


@pytest.mark.asyncio
async def test_store_copies_a_backend_hit_into_memory(fake_redis, clock):
    backend = RedisTokenCache(client=fake_redis)
    await backend.set("k", _token())
    memory = MemoryTokenCache()
    store = TokenStore(backend, memory=memory)
    assert await store.get("k") == _token()
    assert await memory.get("k") == _token()


@pytest.mark.asyncio
async def test_store_delete_reaches_both_layers(fake_redis, clock):
    backend = RedisTokenCache(client=fake_redis)
    memory = MemoryTokenCache()
    store = TokenStore(backend, memory=memory)
    await store.set("k", _token())
    await store.delete("k")
    assert await memory.get("k") is None
    assert await fake_redis.exists("k") == 0


@pytest.mark.asyncio
async def test_store_without_a_backend_is_memory_only(clock):
    store = TokenStore(None, memory=MemoryTokenCache())
    await store.set("k", _token())
    assert await store.get("k") == _token()


@pytest.mark.asyncio
async def test_store_contains_backend_failures_and_warns_once_per_streak(clock, caplog):
    flaky = _Flaky()
    store = TokenStore(flaky, memory=MemoryTokenCache())
    with caplog.at_level(logging.WARNING, logger="gundi_client_v2.token_cache"):
        assert await store.get("k") is None
        await store.set("k", _token())
        assert await store.get("k") == _token()  # memory still serves
        await store.delete("k")
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "_Flaky" in warnings[0].getMessage()
    assert "ConnectionError" in warnings[0].getMessage()
    assert "redis down" not in warnings[0].getMessage()  # no backend text
    assert "k" not in warnings[0].getMessage().split("_Flaky")[0]  # no key
    assert flaky.calls == 3  # get, set, delete all attempted; the memory hit made no backend call


@pytest.mark.asyncio
async def test_stores_sharing_a_backend_share_one_failure_streak(clock, caplog):
    """The runner builds a TokenStore per GundiClient per call; during an outage
    that must not mean a warning per call."""
    flaky = _Flaky()
    with caplog.at_level(logging.WARNING, logger="gundi_client_v2.token_cache"):
        for _ in range(5):
            await TokenStore(flaky, memory=MemoryTokenCache()).get("k")
    assert sum(r.levelno == logging.WARNING for r in caplog.records) == 1


@pytest.mark.asyncio
async def test_store_warns_again_after_the_backend_recovers_and_fails_again(clock, caplog, fake_redis):
    class Toggle:
        def __init__(self):
            self.fail = True
            self.inner = RedisTokenCache(client=fake_redis)

        async def get(self, key):
            if self.fail:
                raise TimeoutError()
            return await self.inner.get(key)

        async def set(self, key, token):
            if self.fail:
                raise TimeoutError()
            await self.inner.set(key, token)

        async def delete(self, key):
            if self.fail:
                raise TimeoutError()
            await self.inner.delete(key)

    toggle = Toggle()
    store = TokenStore(toggle, memory=MemoryTokenCache())
    with caplog.at_level(logging.WARNING, logger="gundi_client_v2.token_cache"):
        await store.get("a")          # fails: warning 1
        await store.get("b")          # fails: suppressed
        toggle.fail = False
        await store.get("c")          # succeeds: streak reset
        toggle.fail = True
        await store.get("d")          # fails: warning 2
    assert sum(r.levelno == logging.WARNING for r in caplog.records) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/client/test_token_cache.py -q -k store`
Expected: FAIL with `ImportError: cannot import name 'TokenStore'`

- [ ] **Step 3: Write the minimal implementation**

Add to `gundi_client_v2/token_cache.py` (add `from typing import Awaitable, Callable, Optional, TypeVar` if you want typing; the code below uses plain names):

```python
class TokenStore:
    """Memory layer in front of one optional backend.

    The cache never raises into an API call: a failing backend is logged at
    warning level once per failure streak (the flag resets on the next
    success) and treated as a miss or a skipped write. The log line names the
    backend class and the exception class, never a key or a token.
    """

    def __init__(self, backend: "TokenCache | None", memory: "MemoryTokenCache | None" = None) -> None:
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


# Backends (by id) currently in a failure streak; shared by every TokenStore so
# an outage logs once per backend, not once per client built during it.
_FAILING_BACKENDS: set = set()
```

Extend `clear_token_cache()` so it also runs `_FAILING_BACKENDS.clear()` (its final body is now `_PROCESS_CACHE.clear(); _BACKENDS.clear(); _FAILING_BACKENDS.clear()`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/client/test_token_cache.py -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add gundi_client_v2/token_cache.py tests/client/test_token_cache.py
git commit -m "feat(token-cache): TokenStore coordinator; backend failures degrade to memory"
```

---

### Task 7: Settings and `GundiClient` constructor wiring

**Files:**
- Modify: `gundi_client_v2/settings.py`
- Modify: `gundi_client_v2/client.py` (constructor, lines ~244-345, and the imports)
- Test: `tests/client/test_token_cache_client.py` (new)

**Interfaces:**
- Consumes: `token_cache_from_url`, `TokenStore`, `TokenCacheConfigError` (Tasks 5, 6)
- Produces:
  - `settings.GUNDI_TOKEN_CACHE_URL` (env `GUNDI_TOKEN_CACHE_URL`, default None)
  - `GundiClient(**kwargs)` accepts `token_cache_url: str | None` (default `settings.GUNDI_TOKEN_CACHE_URL`) and `token_cache: TokenCache | None` (default None; takes precedence)
  - `GundiClient._token_store: TokenStore`

- [ ] **Step 1: Write the failing tests**

```python
# tests/client/test_token_cache_client.py
"""GundiClient behaviour with the shared token cache."""
import asyncio
import logging

import httpx
import pytest
import respx
from fakeredis import FakeAsyncRedis

from gundi_client_v2 import settings
from gundi_client_v2.client import GundiClient
from gundi_client_v2.errors import TokenCacheConfigError
from gundi_client_v2.token_cache import (
    FileTokenCache,
    MemoryTokenCache,
    RedisTokenCache,
    TokenStore,
    clear_token_cache,
)


def test_client_defaults_to_memory_only(client_settings):
    client = GundiClient(**client_settings)
    assert isinstance(client._token_store, TokenStore)
    assert client._token_store._backend is None


def test_client_builds_the_backend_from_the_kwarg_url(client_settings, tmp_path):
    client = GundiClient(**client_settings, token_cache_url=f"file://{tmp_path}")
    assert isinstance(client._token_store._backend, FileTokenCache)


def test_client_reads_the_url_from_settings(client_settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "GUNDI_TOKEN_CACHE_URL", f"file://{tmp_path}")
    client = GundiClient(**client_settings)
    assert isinstance(client._token_store._backend, FileTokenCache)


def test_injected_token_cache_wins_over_the_url(client_settings, tmp_path):
    injected = RedisTokenCache(client=FakeAsyncRedis(decode_responses=True))
    client = GundiClient(**client_settings, token_cache_url=f"file://{tmp_path}", token_cache=injected)
    assert client._token_store._backend is injected


def test_bad_url_fails_at_construction(client_settings):
    with pytest.raises(TokenCacheConfigError):
        GundiClient(**client_settings, token_cache_url="memcached://nope")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/client/test_token_cache_client.py -q`
Expected: 5 FAIL. Four with `AttributeError: 'GundiClient' object has no attribute '_token_store'` (the settings test additionally with `AttributeError: module 'gundi_client_v2.settings' has no attribute 'GUNDI_TOKEN_CACHE_URL'`), and `test_bad_url_fails_at_construction` with `DID NOT RAISE` because the constructor ignores unknown kwargs today.

- [ ] **Step 3: Add the setting**

In `gundi_client_v2/settings.py`, after `OAUTH_SCOPE`:

```python
# Shared OAuth token cache backend: redis://host:port/db, rediss://..., or
# file:///dir. Unset means tokens are shared only within the process.
GUNDI_TOKEN_CACHE_URL = env.str("GUNDI_TOKEN_CACHE_URL", None)
```

- [ ] **Step 4: Wire the constructor**

In `gundi_client_v2/client.py`, add to the imports:

```python
from . import token_cache as _token_cache
```

In `GundiClient.__init__`, extend the docstring's **Authentication settings** with:

```
                **Token cache settings**

                * ``token_cache_url`` (str): Durable token cache backend
                  shared with other processes: ``redis://host:port/db``,
                  ``rediss://…`` or ``file:///dir``. Env:
                  ``GUNDI_TOKEN_CACHE_URL``. Unset means tokens are shared
                  only within this process (always on).
                * ``token_cache`` (TokenCache): An injected backend; takes
                  precedence over ``token_cache_url``.
```

and after the three `self.cached_token*` assignments add:

```python
        # Shared token cache: process-wide memory layer, plus one optional backend.
        backend = kwargs.get("token_cache")
        if backend is None:
            backend = _token_cache.token_cache_from_url(
                kwargs.get("token_cache_url", settings.GUNDI_TOKEN_CACHE_URL)
            )
        self._token_store = _token_cache.TokenStore(backend)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/client/test_token_cache_client.py -q && uv run pytest -q`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add gundi_client_v2/settings.py gundi_client_v2/client.py tests/client/test_token_cache_client.py
git commit -m "feat(client): token_cache_url / token_cache kwargs and GUNDI_TOKEN_CACHE_URL"
```

---

### Task 8: `get_access_token` reads and writes the shared cache

**Files:**
- Modify: `gundi_client_v2/client.py` (`_refresh_token`, `_store_token`, `get_access_token`, lines ~459-600)
- Test: `tests/client/test_token_cache_client.py`

**Interfaces:**
- Consumes: `TokenStore`, `CachedToken`, `token_cache_key`, `NO_REFRESH`, `_token_cache._now`
- Produces (all on `GundiClient`):
  - `_token_cache_key(token_url: str) -> str`
  - `_current_entry() -> CachedToken | None` (the instance attributes as a record, None when no token)
  - `_adopt(entry: CachedToken) -> None` (sets `cached_token`, `cached_token_expires_at`, `cached_token_refresh_expires_at`)
  - `_to_cached(token: OAuthToken, *, refresh_rotated: bool = True, prior: CachedToken | None = None) -> CachedToken` (applies `_expiry_with_buffer`; keeps `prior.refresh_expires_at` when `refresh_rotated` is False)
  - `_store_token(token, *, refresh_rotated=True)` kept, now `self._adopt(self._to_cached(...))`
  - `async _fetch_token(token_url: str, prior: CachedToken | None) -> CachedToken` (refresh grant when `prior.refresh_is_live(now)`, else full authentication; the body of today's `_refresh_token` steps 1 and 2)
  - `async _refresh_token() -> OAuthToken` kept for compatibility: `entry = await self._fetch_token(await self._resolve_token_url(), self._current_entry()); self._adopt(entry); return self.cached_token`
  - `async get_access_token(force_refresh_token=False) -> OAuthToken` per the spec's four steps

- [ ] **Step 1: Write the failing tests**

Append to `tests/client/test_token_cache_client.py`:

```python
TOKEN_URL = "https://fakeauth.com/auth/realms/dev/protocol/openid-connect/token"


def _mock_token_endpoint(mock, auth_token_response):
    return mock.post(TOKEN_URL).respond(status_code=200, json=auth_token_response)


@pytest.mark.asyncio
async def test_two_clients_with_the_same_credentials_share_one_token(client_settings, auth_token_response):
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        first = GundiClient(**client_settings)
        second = GundiClient(**client_settings)
        h1 = await first.get_auth_header()
        h2 = await second.get_auth_header()
    assert h1 == h2
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_concurrent_first_requests_in_one_process_make_one_token_request(client_settings, auth_token_response):
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        clients = [GundiClient(**client_settings) for _ in range(10)]
        headers = await asyncio.gather(*(c.get_auth_header() for c in clients))
    assert len({h["authorization"] for h in headers}) == 1
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_different_secret_gets_its_own_token(client_settings, auth_token_response):
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        await GundiClient(**client_settings).get_auth_header()
        rotated = {**client_settings, "keycloak_client_secret": "rotated-secret"}
        await GundiClient(**rotated).get_auth_header()
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_a_fresh_process_finds_the_token_in_the_backend(client_settings, auth_token_response):
    backend = RedisTokenCache(client=FakeAsyncRedis(decode_responses=True))
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        await GundiClient(**client_settings, token_cache=backend).get_auth_header()
        clear_token_cache()  # simulate a new process: empty memory, same Redis
        await GundiClient(**client_settings, token_cache=backend).get_auth_header()
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_a_fresh_process_finds_the_token_in_the_file_backend(client_settings, auth_token_response, tmp_path):
    url = f"file://{tmp_path}/tokens"
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        await GundiClient(**client_settings, token_cache_url=url).get_auth_header()
        clear_token_cache()
        await GundiClient(**client_settings, token_cache_url=url).get_auth_header()
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_a_process_that_lost_its_memory_layer_re_authenticates_fully(
    client_settings, auth_token_response, monkeypatch
):
    """Memory-only deployment: after the access token expires and the process
    layer is gone, there is no refresh token to use, so it is a full
    authentication. The refresh-grant path is pinned by the backend test below."""
    from datetime import timedelta
    from gundi_client_v2 import token_cache as tc
    from urllib.parse import parse_qs

    base = tc._now()
    clock = {"now": base}
    monkeypatch.setattr(tc, "_now", lambda: clock["now"])
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        await GundiClient(**client_settings).get_auth_header()
        clock["now"] = base + timedelta(seconds=auth_token_response["expires_in"] + 60)
        clear_token_cache()
        await GundiClient(**client_settings).get_auth_header()
    grants = [parse_qs(c.request.content.decode())["grant_type"][0] for c in route.calls]
    assert grants == ["client_credentials", "client_credentials"]


@pytest.mark.asyncio
async def test_refresh_grant_is_used_when_the_backend_holds_a_live_refresh_token(
    client_settings, auth_token_response, monkeypatch
):
    from datetime import timedelta
    from gundi_client_v2 import token_cache as tc
    from urllib.parse import parse_qs

    base = tc._now()
    clock = {"now": base}
    monkeypatch.setattr(tc, "_now", lambda: clock["now"])
    backend = RedisTokenCache(client=FakeAsyncRedis(decode_responses=True))
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        await GundiClient(**client_settings, token_cache=backend).get_auth_header()
        clock["now"] = base + timedelta(seconds=auth_token_response["expires_in"] + 60)
        clear_token_cache()
        await GundiClient(**client_settings, token_cache=backend).get_auth_header()
    grants = [parse_qs(c.request.content.decode())["grant_type"][0] for c in route.calls]
    assert grants == ["client_credentials", "refresh_token"]


@pytest.mark.asyncio
async def test_force_refresh_evicts_the_shared_entry_before_re_authenticating(client_settings, auth_token_response):
    fake = FakeAsyncRedis(decode_responses=True)
    backend = RedisTokenCache(client=fake)
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        client = GundiClient(**client_settings, token_cache=backend)
        await client.get_auth_header()
        keys_before = await fake.keys("gundi-client:token:*")
        # Make the eviction observable: the re-issued token differs.
        route.respond(status_code=200, json={**auth_token_response, "access_token": "second"})
        await client.get_auth_header(force_refresh_token=True)
        keys_after = await fake.keys("gundi-client:token:*")
        stored = await fake.get(keys_after[0])
    assert keys_before == keys_after
    assert '"access_token": "second"' in stored
    assert route.call_count == 2
    # And a sibling client in the same process now sees the new token, not the rejected one.
    sibling = GundiClient(**client_settings, token_cache=backend)
    async with respx.mock as mock:
        _mock_token_endpoint(mock, auth_token_response)
        header = await sibling.get_auth_header()
    assert header["authorization"] == "Bearer second"


@pytest.mark.asyncio
async def test_unreachable_backend_degrades_to_memory_with_one_warning(client_settings, auth_token_response, caplog):
    class Down:
        async def get(self, key):
            raise ConnectionError()

        async def set(self, key, token):
            raise ConnectionError()

        async def delete(self, key):
            raise ConnectionError()

    down = Down()  # the memoized backend every client built from one URL would share
    async with respx.mock as mock:
        route = _mock_token_endpoint(mock, auth_token_response)
        with caplog.at_level(logging.WARNING, logger="gundi_client_v2.token_cache"):
            await GundiClient(**client_settings, token_cache=down).get_auth_header()
            await GundiClient(**client_settings, token_cache=down).get_auth_header()
    assert route.call_count == 1  # memory still shared the token
    assert sum(r.levelno == logging.WARNING for r in caplog.records) == 1


@pytest.mark.asyncio
async def test_the_302_login_redirect_still_retries_with_a_fresh_token(auth_token_response, gundi_client_v2):
    """Regression guard: the existing redirect retry path goes through force_refresh_token."""
    from gundi_core.schemas.v2 import IntegrationType

    payload = {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "name": "Test Integration",
        "value": "test_integration",
        "description": "",
        "actions": [],
    }
    async with respx.mock(assert_all_called=True) as mock:
        token_route = mock.post(gundi_client_v2.oauth_token_url).respond(status_code=200, json=auth_token_response)
        type_url = f"{gundi_client_v2.integrations_endpoint}/types/"
        mock.post(type_url).side_effect = [
            httpx.Response(status_code=302, headers={"location": "https://cdip-auth.pamdas.org/auth/realms/x/protocol/openid-connect/auth"}),
            httpx.Response(status_code=200, json=payload),
        ]
        result = await gundi_client_v2.register_integration_type(payload)
    assert result == IntegrationType.parse_obj(payload)
    assert token_route.call_count == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/client/test_token_cache_client.py -q`
Expected: the sharing tests FAIL with `assert route.call_count == 1` seeing 2 (or 10); the force-refresh and 302 tests may pass already (they exercise existing behaviour), which is acceptable as regression guards.

- [ ] **Step 3: Rewrite the token path in `GundiClient`**

Replace `_refresh_token`, `_store_token` and `get_access_token` (keep `_expiry_with_buffer` and `_resolve_token_url` as they are) with:

```python
    def _grant_type(self) -> str:
        return "password" if (self.username and self.password) else "client_credentials"

    def _token_cache_key(self, token_url: str) -> str:
        return _token_cache.token_cache_key(
            token_url=token_url,
            grant_type=self._grant_type(),
            client_id=self.client_id,
            username=self.username if self._grant_type() == "password" else None,
            audience=self.audience,
            scope=self.scope,
            secret=self.password if self._grant_type() == "password" else self.client_secret,
        )

    def _current_entry(self) -> "_token_cache.CachedToken | None":
        if self.cached_token is None:
            return None
        return _token_cache.CachedToken(
            access_token=self.cached_token.access_token,
            refresh_token=self.cached_token.refresh_token or "",
            token_type=self.cached_token.token_type or "Bearer",
            expires_at=self.cached_token_expires_at,
            refresh_expires_at=self.cached_token_refresh_expires_at,
        )

    def _adopt(self, entry: "_token_cache.CachedToken") -> None:
        """Make ``entry`` this instance's token. Keeps the three public
        attributes the CLI token store and callers read."""
        self.cached_token = entry.to_oauth_token()
        self.cached_token_expires_at = entry.expires_at
        self.cached_token_refresh_expires_at = entry.refresh_expires_at

    def _to_cached(
        self, token: OAuthToken, *, refresh_rotated: bool = True, prior=None
    ) -> "_token_cache.CachedToken":
        # ``refresh_rotated`` is False only when a refresh-grant response omitted a
        # new refresh_token (RFC 6749 §6): the prior refresh token and its lifetime
        # stay valid, so they are carried over.
        now = _token_cache._now()
        expires_at = now + timedelta(seconds=self._expiry_with_buffer(token.expires_in))
        if not refresh_rotated and prior is not None:
            refresh_expires_at = prior.refresh_expires_at
        elif token.refresh_token and token.refresh_expires_in > 0:
            refresh_expires_at = now + timedelta(
                seconds=self._expiry_with_buffer(token.refresh_expires_in)
            )
        else:
            refresh_expires_at = _token_cache.NO_REFRESH
        return _token_cache.CachedToken(
            access_token=token.access_token,
            refresh_token=token.refresh_token or "",
            token_type=token.token_type or "Bearer",
            expires_at=expires_at,
            refresh_expires_at=refresh_expires_at,
        )

    def _store_token(self, token, *, refresh_rotated=True):
        """Compatibility wrapper: adopt ``token`` onto this instance only."""
        self._adopt(self._to_cached(token, refresh_rotated=refresh_rotated, prior=self._current_entry()))

    async def _fetch_token(self, token_url: str, prior) -> "_token_cache.CachedToken":
        """Get a token from the IdP: the refresh grant when ``prior`` holds a live
        refresh token, otherwise a full authentication."""
        now = _token_cache._now()
        # 1. Prefer the refresh-token grant when we hold a live refresh token.
        if prior is not None and prior.refresh_is_live(now):
            try:
                token, refresh_rotated = await auth.refresh_access_token(
                    session=self._session,
                    oauth_token_url=token_url,
                    client_id=self.client_id,
                    refresh_token=prior.refresh_token,
                    fallback=prior.to_oauth_token(),
                    # Public/password clients must not send a secret on refresh.
                    client_secret=(
                        None if (self.username and self.password) else self.client_secret
                    ),
                    scope=self.scope,
                )
                return self._to_cached(token, refresh_rotated=refresh_rotated, prior=prior)
            except errors.AuthenticationError:
                logger.info(
                    "Refresh-token grant failed; falling back to full re-authentication."
                )
        # 2. Full authentication. Password grant wins when user credentials are present.
        # A client_id is required for every grant we support, so guard the password
        # branch on it too — otherwise we'd send a half-formed request and let the IdP
        # reject it remotely instead of failing locally with a clear configuration error.
        if self.username and self.password and self.client_id:
            logger.debug("Authenticating via password grant.")
            token = await auth.get_access_token_password_grant(
                session=self._session,
                oauth_token_url=token_url,
                client_id=self.client_id,
                username=self.username,
                password=self.password,
                audience=self.audience,
                scope=self.scope,
            )
        elif self.client_id and self.client_secret:
            logger.debug("Authenticating via client_credentials grant.")
            token = await auth.get_access_token_client_credentials(
                session=self._session,
                oauth_token_url=token_url,
                client_id=self.client_id,
                client_secret=self.client_secret,
                audience=self.audience,
                scope=self.scope,
            )
        else:
            raise errors.AuthenticationError(
                "No credentials configured. Provide a client_id with either "
                "username/password (public client) or client_secret (confidential client)."
            )
        return self._to_cached(token)

    async def _refresh_token(self):
        """Compatibility wrapper around _fetch_token for callers of the old name."""
        entry = await self._fetch_token(await self._resolve_token_url(), self._current_entry())
        self._adopt(entry)
        return self.cached_token

    async def get_access_token(self, force_refresh_token: bool = False) -> OAuthToken:
        """Return a valid OAuth access token, reusing one from the shared cache
        when possible and refreshing or re-authenticating when necessary.

        Lookup order: this instance's token, the process-wide memory layer, the
        configured backend (Redis or file), then the IdP (refresh grant when a
        live refresh token is known, else full authentication). Whatever is
        fetched is written to every layer. ``force_refresh_token=True`` (a 401,
        or the login redirect) first evicts the shared entry so no other client
        or replica keeps serving a token the server has rejected.

        Args:
            force_refresh_token: When ``True``, evict the cached entry and
                fetch a fresh token from the IdP.

        Returns:
            A valid ``OAuthToken``.

        Raises:
            AuthenticationError: If no credentials are configured or the IdP
                rejects the request.
        """
        now = _token_cache._now()
        if (
            not force_refresh_token
            and self.cached_token is not None
            and self.cached_token_expires_at > now
        ):
            return self.cached_token
        token_url = await self._resolve_token_url()
        key = self._token_cache_key(token_url)
        async with self._token_store.lock(key):
            prior = self._current_entry()
            if force_refresh_token:
                await self._token_store.delete(key)
            else:
                shared = await self._token_store.get(key)
                if shared is not None:
                    if shared.is_live(_token_cache._now()):
                        self._adopt(shared)
                        return self.cached_token
                    prior = shared  # expired access token; its refresh token may still work
            entry = await self._fetch_token(token_url, prior)
            await self._token_store.set(key, entry)
            self._adopt(entry)
            return self.cached_token
```

Keep the remainder of the class (`get_auth_header`, `_get`, `_post`, `_patch`, `_delete`, API methods) unchanged.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: all passed. If `tests/client/test_password_grant.py` or `tests/client/test_auth.py` fail on a `_refresh_token` / `_store_token` attribute, the compatibility wrappers above are misnamed; fix the wrapper, not the test.

- [ ] **Step 5: Format and lint**

Run: `uv run black gundi_client_v2 tests && uv run black --check .`
Expected: reformatted files listed, then `All done!`

- [ ] **Step 6: Commit**

```bash
git add gundi_client_v2/client.py tests/client/test_token_cache_client.py
git commit -m "feat(client): get_access_token reads and writes the shared token cache"
```

---

### Task 9: Public exports, version 3.7.0, documentation

**Files:**
- Modify: `gundi_client_v2/__init__.py`
- Create: `docs/authentication/token-cache.md`
- Modify: `mkdocs.yml` (nav under Authentication and API reference), `README.md` (configuration table), `docs/authentication/refresh-and-errors.md` (token lifecycle section), `docs/api-reference/auth.md`
- Test: `tests/client/test_token_cache_client.py`

**Interfaces:**
- Produces: `from gundi_client_v2 import token_cache`; `gundi_client_v2.__version__ == "3.7.0"`; `gundi_client_v2.TokenCacheConfigError`

- [ ] **Step 1: Write the failing test**

Append to `tests/client/test_token_cache_client.py`:

```python
def test_public_exports_and_version():
    import gundi_client_v2

    assert gundi_client_v2.__version__ == "3.7.0"
    assert gundi_client_v2.TokenCacheConfigError is TokenCacheConfigError
    from gundi_client_v2 import token_cache

    assert token_cache.MemoryTokenCache is MemoryTokenCache
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/client/test_token_cache_client.py::test_public_exports_and_version -q`
Expected: FAIL on `__version__ == "3.7.0"` (currently 3.6.3)

- [ ] **Step 3: Update `gundi_client_v2/__init__.py`**

```python
__version__ = "3.7.0"

from .client import GundiClient, GundiDataSenderClient
from .errors import GundiClientError, AuthenticationError, GundiAPIError, TokenCacheConfigError
from . import errors
from . import token_cache
```

- [ ] **Step 4: Write `docs/authentication/token-cache.md`**

```markdown
# Shared token cache

Every `GundiClient` shares one OAuth token per set of credentials.

## Why

Without a shared cache, each `GundiClient` instance requests its own token and
forgets it when the instance goes away. Services that build a client per call
mint a new Keycloak token for nearly every request, although the token would be
valid for hours or days. The cache keeps that token and hands it to every client
that has the same credentials, for as long as it is valid.

## Layers

**Process memory (always on).** Every client in a process reads and writes one
in-memory table keyed by credentials. Concurrent clients that miss at the same
moment wait for one token request instead of each making their own. Nothing to
configure. `gundi_client_v2.token_cache.clear_token_cache()` empties it (tests,
or a long-running process that must drop every cached token).

**One durable backend (optional).** Chosen by `GUNDI_TOKEN_CACHE_URL` or the
`token_cache_url=` kwarg:

| URL | Backend | Use it for |
|---|---|---|
| `redis://host:port/db`, `rediss://…` | Redis (`pip install gundi-client-v2[redis]`) | Several replicas or processes sharing one Redis |
| `file:///absolute/dir` | One private file per credential set (0700 dir, 0600 files) | Local runs, scripts, hosts without Redis |
| unset | none | Tokens shared within the process only |

`token_cache=` accepts any object with async `get(key)`, `set(key, token)` and
`delete(key)` and takes precedence over the URL.

There is no fallback chain. When the backend is unreachable the client logs one
warning per outage and runs on the memory layer until it recovers; the cache
never raises into an API call. A bad URL, or `redis://` without the `redis`
package, raises `TokenCacheConfigError` when the client is constructed.

## What is shared, and with whom

The cache key is a SHA-256 over the resolved token endpoint, grant type, client
id, username (password grant), audience, scope, and the secret. Two clients
share a token exactly when all of those match. Rotating a secret produces a new
key, so a token minted under the old secret is never reused. The key reveals
nothing about the credentials.

In Redis, entries expire with the later of the access-token and refresh-token
lifetimes. A token the API has rejected (a 401, or the login redirect) is evicted
from every layer before the client re-authenticates, so no other replica keeps
serving it.

## Security

Access tokens are bearer credentials. Point the Redis backend at a database that
is as protected as the rest of your service's Redis data, and treat the file
backend's directory as you would a credentials file. The secret itself never
leaves the process; it enters the cache key only inside a one-way hash.

## Example

```python
from gundi_client_v2 import GundiClient

# All three share one token: same credentials, same process.
a = GundiClient()
b = GundiClient()
c = GundiClient(token_cache_url="redis://redis:6379/2")  # and with other replicas
```
```

- [ ] **Step 5: Update the other docs**

In `mkdocs.yml`, under the Authentication nav after `Refresh and errors`, add `    - Shared token cache: authentication/token-cache.md`.

In `README.md`, in the configuration table that lists `OAUTH_SCOPE`, add a row:

```
| `GUNDI_TOKEN_CACHE_URL` | Durable token cache shared across processes: `redis://host:port/db`, `rediss://…` (needs `gundi-client-v2[redis]`) or `file:///dir`. Unset shares tokens within the process only. See [Shared token cache](docs/authentication/token-cache.md). | — |
```

and in the kwargs table a row `| \`token_cache_url\` | \`GUNDI_TOKEN_CACHE_URL\` | Token cache backend URL. \`token_cache=\` injects a backend object instead. |`.

In `docs/authentication/refresh-and-errors.md`, replace the first paragraph of "Token lifecycle inside `GundiClient`" with:

```markdown
The client keeps the most recent `OAuthToken` on the instance and in a
process-wide cache shared by every `GundiClient` with the same credentials
(optionally also in Redis or a file; see [Shared token cache](token-cache.md)),
along with two computed timestamps:
```

In `docs/api-reference/auth.md`, add at the end:

```markdown
## `gundi_client_v2.token_cache`

::: gundi_client_v2.token_cache
    options:
      members:
        - CachedToken
        - TokenCache
        - MemoryTokenCache
        - RedisTokenCache
        - FileTokenCache
        - TokenStore
        - token_cache_from_url
        - token_cache_key
        - clear_token_cache
```

Run `grep -n ':::' docs/api-reference/auth.md` first: if that file's existing blocks use `options:` with `members:`, keep the block above as written; if they use the bare `::: module.path` form with no options, use `::: gundi_client_v2.token_cache` alone and let mkdocstrings render every public name.

- [ ] **Step 6: Run the tests, black, and the docs build**

Run: `uv run pytest -q && uv run black --check . && uv run --extra docs mkdocs build --strict -q`
Expected: all passed; `All done!`; docs build with no warnings (a broken nav link fails `--strict`).

- [ ] **Step 7: Commit**

```bash
git add gundi_client_v2/__init__.py docs/authentication/token-cache.md mkdocs.yml README.md docs/authentication/refresh-and-errors.md docs/api-reference/auth.md
git commit -m "docs: shared token cache; bump version to 3.7.0"
```

- [ ] **Step 8: Push and open the PR**

```bash
git push -u origin cd/token-cache
gh pr create --repo PADAS/gundi-client --base v2 --title "feat: shared OAuth token cache (memory + Redis/file backend)" --body-file docs/superpowers/specs/2026-09-08-token-cache-design.md
```

Then release 3.7.0 the way `.github/workflows/release.yml` expects (tag `v3.7.0` after merge; see the `chore/bump-3.6.3` branch for the previous release's shape).

---

## Part B — gundi-integration-action-runner (separate repo and PR; needs 3.7.0 on PyPI)

Work in `/Users/chrisdo/padas/gundi-integration-action-runner/.worktrees/token-cache` (`git worktree add .worktrees/token-cache -b cd/token-cache origin/main`). Tests: `../../.venv/bin/python -m pytest -q` from the worktree (baseline on main as of 2026-09-08: 217 passed; re-run before starting to get the current number). Lockfile: `pip-compile --output-file=requirements.txt requirements-base.in requirements-dev.in requirements.in`.

### Task 10: Bump gundi-client-v2 to 3.7 with the fastapi/httpx quadruple

**Files:**
- Modify: `requirements-base.in`, `requirements.txt` (regenerated)

- [ ] **Step 1: Edit the pins**

In `requirements-base.in` replace

```
fastapi~=0.103.2
...
gundi-client-v2~=2.4.0
# httpx is imported directly by app/services/*; ~=0.24.1 keeps the resolver on
# gundi-client-v2 2.4.0 — 2.4.1 requires httpx 0.28, which breaks the TestClient
# shipped with starlette 0.27 (pinned via fastapi~=0.103.2)
httpx~=0.24.1
```

with

```
fastapi~=0.115.0
...
# [redis] extra: the runner points the client's shared token cache at its Redis
# (settings.GUNDI_TOKEN_CACHE_URL). 3.x needs httpx 0.28, which needs the
# starlette that ships with fastapi 0.115 (see gundi-client MIGRATION.md).
gundi-client-v2[redis]~=3.7.0
# httpx is imported directly by app/services/*
httpx~=0.28.1
```

- [ ] **Step 2: Regenerate the lockfile and install**

Run: `pip-compile --output-file=requirements.txt requirements-base.in requirements-dev.in requirements.in && ../../.venv/bin/python -m pip install -q -r requirements.txt -r requirements-dev.txt`
Expected: resolves; `gundi-client-v2==3.7.0`, `fastapi==0.115.x`, `starlette>=0.37`, `httpx==0.28.x` in `requirements.txt`.

- [ ] **Step 3: Run the suite**

Run: `../../.venv/bin/python -m pytest -q`
Expected: all passed. A `TypeError: Client.__init__() got an unexpected keyword argument 'app'` means starlette is still below 0.37; raise the fastapi pin.

- [ ] **Step 4: Commit**

```bash
git add requirements-base.in requirements.txt
git commit -m "chore: gundi-client-v2 3.7 with the redis extra; fastapi 0.115 / httpx 0.28"
```

### Task 11: Settings, one client factory, and every construction site through it

**Files:**
- Modify: `app/settings/base.py` (after `REDIS_CONFIGS_DB`)
- Create: `app/services/gundi_client.py`
- Modify: `app/services/gundi.py:74` (`_get_gundi_api_key`), `app/services/config_manager.py:96` (`_fetch_integration_from_gundi`), `app/services/action_runner.py:31` (`_portal`)
- Modify: `app/conftest.py` (autouse fixture)
- Test: `app/services/tests/test_gundi_client.py` (new)

**Interfaces:**
- Produces: `settings.REDIS_TOKEN_CACHE_DB: int` (default 2), `settings.GUNDI_TOKEN_CACHE_URL: str` (default `redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_TOKEN_CACHE_DB}`), `app.services.gundi_client.new_gundi_client(**kwargs) -> GundiClient`

**Ship Tasks 10 and 11 in the same template PR.** The `gundi-client-v2[redis]`
requirement (Task 10) and the `GUNDI_TOKEN_CACHE_URL` default (Task 11) are one
change: a `redis://` URL without the extra installed raises
`TokenCacheConfigError` in `GundiClient.__init__`, so splitting them would break
client construction on every replica at startup, not just on the first token
request.

- [ ] **Step 1: Write the failing tests**

```python
# app/services/tests/test_gundi_client.py
import pytest

from app import settings
from app.services.gundi_client import new_gundi_client


def test_default_token_cache_url_composes_from_the_redis_settings():
    import importlib
    from app.settings import base

    assert base.GUNDI_TOKEN_CACHE_URL == f"redis://{base.REDIS_HOST}:{base.REDIS_PORT}/{base.REDIS_TOKEN_CACHE_DB}"
    assert base.REDIS_TOKEN_CACHE_DB == 2


def test_factory_passes_the_configured_url_through(mocker):
    from gundi_client_v2.token_cache import RedisTokenCache

    mocker.patch.object(settings, "GUNDI_TOKEN_CACHE_URL", "redis://token-cache:6379/2")
    client = new_gundi_client()
    assert isinstance(client._token_store._backend, RedisTokenCache)


def test_factory_with_no_url_is_memory_only(mocker):
    mocker.patch.object(settings, "GUNDI_TOKEN_CACHE_URL", None)
    client = new_gundi_client()
    assert client._token_store._backend is None


def test_every_gundi_client_construction_goes_through_the_factory():
    """Grep guard: a new GundiClient() call site would bypass the shared cache."""
    import pathlib

    offenders = []
    for path in pathlib.Path("app").rglob("*.py"):
        if "tests" in path.parts or path.name == "gundi_client.py":
            continue
        text = path.read_text()
        if "GundiClient(" in text:
            offenders.append(str(path))
    assert offenders == [], offenders
```

- [ ] **Step 2: Run them to verify they fail**

Run: `../../.venv/bin/python -m pytest app/services/tests/test_gundi_client.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.gundi_client'` and the grep guard listing `app/services/gundi.py`, `app/services/config_manager.py`, `app/services/action_runner.py`

- [ ] **Step 3: Add the settings**

In `app/settings/base.py`, after `REDIS_CONFIGS_DB`:

```python
# Shared OAuth token cache for GundiClient (gundi-client-v2 >= 3.7): one
# Keycloak token per set of credentials, shared by every replica through this
# Redis database. Set GUNDI_TOKEN_CACHE_URL explicitly to point elsewhere, or
# to an empty value to keep tokens per process.
REDIS_TOKEN_CACHE_DB = env.int("REDIS_TOKEN_CACHE_DB", 2)
GUNDI_TOKEN_CACHE_URL = env.str(
    "GUNDI_TOKEN_CACHE_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_TOKEN_CACHE_DB}"
) or None
```

Confirm `app/settings/__init__.py` re-exports everything from `base` (`from .base import *` or explicit names); if names are explicit, add both.

- [ ] **Step 4: Create the factory**

```python
# app/services/gundi_client.py
"""The one way this service builds a GundiClient.

Every instance shares the process-wide token cache and the Redis token cache
this deployment configures (settings.GUNDI_TOKEN_CACHE_URL), so the runner
requests one Keycloak token per set of credentials instead of one per call.
Nothing else in app/ constructs GundiClient directly; a test guards that.
"""
from gundi_client_v2.client import GundiClient

from app import settings


def new_gundi_client(**kwargs) -> GundiClient:
    kwargs.setdefault("token_cache_url", settings.GUNDI_TOKEN_CACHE_URL)
    return GundiClient(**kwargs)
```

- [ ] **Step 5: Route the three construction sites through it**

`app/services/gundi.py`: change the import line to `from gundi_client_v2.client import GundiDataSenderClient` and add `from .gundi_client import new_gundi_client`; in `_get_gundi_api_key` replace `async with GundiClient() as gundi_client:` with `async with new_gundi_client() as gundi_client:`.

`app/services/config_manager.py`: replace the `GundiClient` import with `from .gundi_client import new_gundi_client` and `async with GundiClient() as gundi:` with `async with new_gundi_client() as gundi:`.

`app/services/action_runner.py`: replace the `GundiClient` import with `from .gundi_client import new_gundi_client` and `_portal = GundiClient()` with `_portal = new_gundi_client()`.

Then grep for any test that patches `app.services.gundi.GundiClient`, `app.services.config_manager.GundiClient` or `app.services.action_runner.GundiClient` (`grep -rn "GundiClient" app --include='*.py' | grep tests`) and repoint those patches at `app.services.gundi_client.GundiClient`, which is the name the factory resolves at call time.

- [ ] **Step 6: Keep tests off Redis**

In `app/conftest.py`, add an autouse fixture near the top:

```python
@pytest.fixture(autouse=True)
def _memory_only_token_cache(mocker):
    """Tests never reach a Redis; the client's shared token cache stays in-process."""
    from app import settings as _settings

    mocker.patch.object(_settings, "GUNDI_TOKEN_CACHE_URL", None)
    from gundi_client_v2.token_cache import clear_token_cache

    clear_token_cache()
    yield
    clear_token_cache()
```

Note: `_portal` is built at import time with the default Redis URL; `redis.asyncio.Redis.from_url` does not connect until the first command, and no test drives `_portal` against a real endpoint, so this is safe. The fixture covers every client built during a test.

The `clear_token_cache()` calls in that fixture are required, not optional: the
library's memory layer is always on and process-wide, so without them a token
cached by one test leaks into the next. Any test that counts token requests, or
that runs concurrent fetches (per-test event loops each need their own per-key
lock), depends on starting from an empty layer.

- [ ] **Step 7: Run the suite**

Run: `../../.venv/bin/python -m pytest -q`
Expected: all passed, including the four new tests.

- [ ] **Step 8: Document the settings**

In `README.md`, in the section that lists environment variables (search for `REDIS_HOST`; if the README has no such section, add a short "Token cache" subsection under configuration), add:

```markdown
### Shared Gundi token cache

The runner asks Keycloak for one token per set of credentials and shares it
across replicas through Redis (`gundi-client-v2` 3.7+). It uses the same
`REDIS_HOST` / `REDIS_PORT` as the state and config caches, in database
`REDIS_TOKEN_CACHE_DB` (default `2`). Set `GUNDI_TOKEN_CACHE_URL` to point the
cache elsewhere (`redis://…`, `rediss://…`, `file:///dir`), or to an empty value
to keep tokens per process.
```

- [ ] **Step 9: Commit, push, open the PR**

```bash
git add app/settings/base.py app/services/gundi_client.py app/services/gundi.py app/services/config_manager.py app/services/action_runner.py app/conftest.py app/services/tests/test_gundi_client.py README.md
git commit -m "feat: share one Gundi token per credentials across replicas via the client's Redis token cache"
git push -u origin cd/token-cache
gh pr create --repo PADAS/gundi-integration-action-runner --base main --title "feat: shared Gundi token cache through the runner's Redis" --fill
```

Downstream (EarthRanger, cmore) pick this up through their normal `git merge upstream/main` sync; cmore already runs fastapi 0.115 / httpx 0.28, so only the client pin moves there.

---

## Self-review notes

- Spec coverage: components (Tasks 1-6), key (2), client changes (7-8), failure handling (6, tested again in 8), security (4, 2, docs in 9), configuration (7, 9), template (10-11), testing list (spread across 3-8 and 11), version and changelog (9; the changelog itself lives in GitHub Releases per `docs/changelog.md`, so the release notes are written at tag time). Out-of-scope items are not planned.
- Names used consistently: `CachedToken`, `TokenCache`, `MemoryTokenCache`, `FileTokenCache`, `RedisTokenCache`, `TokenStore`, `token_cache_key`, `token_cache_from_url`, `clear_token_cache`, `TokenCacheConfigError`, `_token_store`, `_fetch_token`, `_adopt`, `_to_cached`, `_current_entry`, `_token_cache_key`, `new_gundi_client`, `GUNDI_TOKEN_CACHE_URL`, `REDIS_TOKEN_CACHE_DB`.
- Two fixes from the plan self-review: backends are memoized per URL (Task 5) so a runner that builds a client per call does not open a Redis pool per call, and the failure-streak flag is keyed by backend object (Task 6) so an outage warns once per process, not once per client.
- One deliberate judgement call recorded in Task 8: an entry whose access token expired but whose refresh token is live is returned by the memory and file layers (and by Redis until its TTL), so the refresh grant can use it; the client treats it as `prior` for the fetch.
