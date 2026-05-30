# OIDC Discovery + Drop uma-ticket Grant — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Keycloak-specific token-URL derivation with OIDC discovery, and replace the uma-ticket grant with standard `client_credentials`, so the library works against any OIDC-compliant IdP (Keycloak, Auth0, …) with no IdP-specific paths.

**Architecture:** Discovery is a single new async function in `auth.py` with a module-level dict cache keyed by `issuer.rstrip("/")` and a `clear_discovery_cache()` helper. `GundiClient` gains an `oauth_issuer` kwarg and an internal `_resolve_token_url()` method that prefers explicit `oauth_token_url`, falls back to discovery, errors if neither is set. The confidential-client branch in `_refresh_token` now calls a new `get_access_token_client_credentials` (replacing `get_access_token`/uma-ticket). `_store_token` learns to handle refreshless tokens.

**Tech Stack:** Python ≥3.10, httpx (async), pydantic v1 via `gundi-core` `OAuthToken`, uv/hatchling, pytest + pytest-asyncio + respx.

**Spec:** `docs/superpowers/specs/2026-05-29-gundi-client-v2-oidc-discovery-design.md`

**Base branch:** This PR branches from `cd/v2-docs` (the current top of the open stack). After `cd/v2-docs` merges into `v2`, GitHub auto-retargets this PR's base; rebase if needed.

---

## Conventions

- Run tests with the project venv: `./.venv/bin/python -m pytest -q`
- All token-endpoint and discovery interactions are **respx-mocked** (no live network).
- Commit messages end with:
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
- Strict TDD: write the failing test, watch it fail, implement, watch it pass, commit. Each task lists steps in that order.

---

### Task 1 — Cut the branch

**Files:** (none — branch operation only)

- [ ] **Step 1: Branch from the current top of stack**

```bash
git fetch origin
git checkout -b cd/v2-oidc-discovery cd/v2-docs
```

- [ ] **Step 2: Confirm the baseline suite is green**

```bash
./.venv/bin/python -m pytest -q
```
Expected: `40 passed`. If not green, stop and investigate before proceeding.

---

### Task 2 — Settings: drop the Keycloak-shaped derivation; read `OAUTH_TOKEN_URL` from env directly

**Files:**
- Modify: `gundi_client_v2/settings.py`

- [ ] **Step 1: Write the failing test**

Create `tests/client/test_settings.py`:
```python
import importlib

from gundi_client_v2 import settings as settings_module


def test_oauth_token_url_read_directly_from_env(monkeypatch):
    monkeypatch.setenv("OAUTH_TOKEN_URL", "https://idp.example.com/oauth/token")
    monkeypatch.delenv("OAUTH_ISSUER", raising=False)
    monkeypatch.delenv("KEYCLOAK_ISSUER", raising=False)
    reloaded = importlib.reload(settings_module)
    try:
        assert reloaded.OAUTH_TOKEN_URL == "https://idp.example.com/oauth/token"
        assert reloaded.OAUTH_ISSUER is None
    finally:
        importlib.reload(settings_module)


def test_oauth_token_url_no_longer_derived_from_issuer(monkeypatch):
    monkeypatch.setenv("OAUTH_ISSUER", "https://idp.example.com/realms/x")
    monkeypatch.delenv("OAUTH_TOKEN_URL", raising=False)
    monkeypatch.delenv("KEYCLOAK_ISSUER", raising=False)
    reloaded = importlib.reload(settings_module)
    try:
        # The settings layer no longer derives the token URL — that's the client's job now,
        # via OIDC discovery.
        assert reloaded.OAUTH_ISSUER == "https://idp.example.com/realms/x"
        assert reloaded.OAUTH_TOKEN_URL is None
    finally:
        importlib.reload(settings_module)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/client/test_settings.py -v`
Expected: FAIL — `OAUTH_TOKEN_URL` is currently `f"{OAUTH_ISSUER}/protocol/openid-connect/token"`, not read directly from env.

- [ ] **Step 3: Replace the OAUTH_TOKEN_URL derivation with a direct env read**

In `gundi_client_v2/settings.py`, replace this block:
```python
# OAuth settings — OAUTH_* preferred; KEYCLOAK_* accepted for backward compatibility
OAUTH_ISSUER = env.str("OAUTH_ISSUER", env.str("KEYCLOAK_ISSUER", None))
OAUTH_TOKEN_URL = f"{OAUTH_ISSUER}/protocol/openid-connect/token" if OAUTH_ISSUER else None
OAUTH_CLIENT_ID = env.str("OAUTH_CLIENT_ID", env.str("KEYCLOAK_CLIENT_ID", None))
```
with:
```python
# OAuth settings — OAUTH_* preferred; KEYCLOAK_* accepted for backward compatibility.
# The token URL is either set directly via OAUTH_TOKEN_URL or discovered at runtime
# from OAUTH_ISSUER via the OIDC discovery document.
OAUTH_ISSUER = env.str("OAUTH_ISSUER", env.str("KEYCLOAK_ISSUER", None))
OAUTH_TOKEN_URL = env.str("OAUTH_TOKEN_URL", None)
OAUTH_CLIENT_ID = env.str("OAUTH_CLIENT_ID", env.str("KEYCLOAK_CLIENT_ID", None))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/client/test_settings.py -v && ./.venv/bin/python -m pytest -q`
Expected: settings tests PASS; full suite PASS (existing tests pass `oauth_token_url` directly as a kwarg, so they're unaffected by the env-derivation change).

- [ ] **Step 5: Commit**

```bash
git add gundi_client_v2/settings.py tests/client/test_settings.py
git commit -m "refactor: read OAUTH_TOKEN_URL directly from env; drop keycloak-shaped derivation

The settings layer no longer derives OAUTH_TOKEN_URL from OAUTH_ISSUER via a
hardcoded Keycloak path. Discovery now happens at the client layer (in a later
task) so the same code can resolve token URLs across Keycloak, Auth0, and any
other OIDC-compliant IdP.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3 — `auth.discover_token_endpoint` + cache + `clear_discovery_cache`

**Files:**
- Modify: `gundi_client_v2/auth.py`
- Create: `tests/client/test_oidc_discovery.py`
- Modify: `tests/conftest.py` (add autouse fixture clearing the cache)

- [ ] **Step 1: Write the failing tests**

Create `tests/client/test_oidc_discovery.py`:
```python
import httpx
import pytest
import respx

from gundi_client_v2 import auth, errors


@pytest.mark.asyncio
async def test_discover_token_endpoint_success():
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    expected = "https://idp.example.com/realms/dev/protocol/openid-connect/token"
    async with respx.mock as mock:
        mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer, "token_endpoint": expected},
        )
        async with httpx.AsyncClient() as session:
            result = await auth.discover_token_endpoint(session, issuer)
        assert result == expected


@pytest.mark.asyncio
async def test_discover_token_endpoint_uses_cache_on_second_call():
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    expected = "https://idp.example.com/realms/dev/protocol/openid-connect/token"
    async with respx.mock as mock:
        route = mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer, "token_endpoint": expected},
        )
        async with httpx.AsyncClient() as session:
            first = await auth.discover_token_endpoint(session, issuer)
            second = await auth.discover_token_endpoint(session, issuer)
        assert first == second == expected
        assert route.call_count == 1  # second call must NOT hit the network


@pytest.mark.asyncio
async def test_discover_token_endpoint_trailing_slash_shares_cache_entry():
    issuer_plain = "https://idp.example.com/realms/dev"
    issuer_slash = "https://idp.example.com/realms/dev/"
    discovery_url = f"{issuer_plain}/.well-known/openid-configuration"
    expected = "https://idp.example.com/realms/dev/protocol/openid-connect/token"
    async with respx.mock as mock:
        route = mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer_plain, "token_endpoint": expected},
        )
        async with httpx.AsyncClient() as session:
            a = await auth.discover_token_endpoint(session, issuer_plain)
            b = await auth.discover_token_endpoint(session, issuer_slash)
        assert a == b == expected
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_discover_token_endpoint_5xx_raises_authentication_error():
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    async with respx.mock as mock:
        mock.get(discovery_url).respond(status_code=503, text="Service Unavailable")
        async with httpx.AsyncClient() as session:
            with pytest.raises(errors.AuthenticationError) as exc:
                await auth.discover_token_endpoint(session, issuer)
        assert "OIDC discovery failed" in str(exc.value)
        assert issuer in str(exc.value)


@pytest.mark.asyncio
async def test_discover_token_endpoint_missing_token_endpoint_raises():
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    async with respx.mock as mock:
        mock.get(discovery_url).respond(
            status_code=httpx.codes.OK, json={"issuer": issuer}  # no token_endpoint
        )
        async with httpx.AsyncClient() as session:
            with pytest.raises(errors.AuthenticationError) as exc:
                await auth.discover_token_endpoint(session, issuer)
        assert "missing 'token_endpoint'" in str(exc.value)


@pytest.mark.asyncio
async def test_clear_discovery_cache_invalidates_cached_entry():
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    expected = "https://idp.example.com/realms/dev/protocol/openid-connect/token"
    async with respx.mock as mock:
        route = mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer, "token_endpoint": expected},
        )
        async with httpx.AsyncClient() as session:
            await auth.discover_token_endpoint(session, issuer)
            auth.clear_discovery_cache()
            await auth.discover_token_endpoint(session, issuer)
        assert route.call_count == 2  # cache was cleared → second call re-fetches
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/client/test_oidc_discovery.py -v`
Expected: FAIL — `auth.discover_token_endpoint` and `auth.clear_discovery_cache` don't exist yet (`AttributeError`).

- [ ] **Step 3: Add the discovery module to `auth.py`**

Append to `gundi_client_v2/auth.py` (after `refresh_access_token`):

```python


_DISCOVERY_CACHE: dict[str, str] = {}


def clear_discovery_cache() -> None:
    """Clear the OIDC discovery cache. Useful for tests and for long-running
    processes that need to pick up an IdP configuration change without a restart."""
    _DISCOVERY_CACHE.clear()


async def discover_token_endpoint(session, issuer: str) -> str:
    """Fetch the OIDC discovery document at ``{issuer}/.well-known/openid-configuration``
    and return its ``token_endpoint``. Cached per-issuer for the process lifetime;
    call :func:`clear_discovery_cache` to invalidate.

    The cache key is ``issuer.rstrip('/')`` so values differing only by a trailing
    slash share one cache entry.
    """
    key = issuer.rstrip("/")
    if key in _DISCOVERY_CACHE:
        return _DISCOVERY_CACHE[key]
    discovery_url = f"{key}/.well-known/openid-configuration"
    try:
        response = await session.get(discovery_url)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise AuthenticationError(
            f"OIDC discovery failed for {issuer}: {e}"
        ) from e
    try:
        token_endpoint = response.json()["token_endpoint"]
    except (ValueError, KeyError, TypeError) as e:
        raise AuthenticationError(
            f"OIDC discovery document at {discovery_url} is missing 'token_endpoint'"
        ) from e
    _DISCOVERY_CACHE[key] = token_endpoint
    return token_endpoint
```

- [ ] **Step 4: Add the autouse cache-clear fixture to `conftest.py`**

In `tests/conftest.py`, add at the top of the file (after the existing imports):

```python
@pytest.fixture(autouse=True)
def _clear_oidc_discovery_cache():
    """Keep the per-issuer OIDC discovery cache test-isolated."""
    from gundi_client_v2 import auth as _auth
    _auth.clear_discovery_cache()
    yield
    _auth.clear_discovery_cache()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/client/test_oidc_discovery.py -v && ./.venv/bin/python -m pytest -q`
Expected: discovery tests PASS; full suite PASS.

- [ ] **Step 6: Commit**

```bash
git add gundi_client_v2/auth.py tests/client/test_oidc_discovery.py tests/conftest.py
git commit -m "feat: OIDC discovery for token_endpoint with module-level cache

Adds auth.discover_token_endpoint which fetches the OIDC discovery document at
{issuer}/.well-known/openid-configuration and returns its token_endpoint.
Results are cached process-lifetime, keyed by issuer.rstrip('/'). A public
clear_discovery_cache() helper provides an escape hatch for long-running
processes and is wired into a tests/conftest.py autouse fixture for test
isolation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4 — `GundiClient.oauth_issuer` kwarg + `_resolve_token_url`

**Files:**
- Modify: `gundi_client_v2/client.py` (constructor + new method)
- Test: `tests/client/test_oidc_discovery.py` (add e2e resolution tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/client/test_oidc_discovery.py`:
```python
from urllib.parse import parse_qs
from gundi_client_v2.client import GundiClient


@pytest.mark.asyncio
async def test_explicit_oauth_token_url_skips_discovery(auth_token_response):
    explicit = "https://idp.example.com/explicit/token"
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    client = GundiClient(
        oauth_token_url=explicit,
        oauth_issuer=issuer,
        oauth_client_id="public-client",
        username="alice",
        password="s3cret",
        base_url="https://api.fakeportal.com",
    )
    async with respx.mock as mock:
        discovery_route = mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer, "token_endpoint": "https://wrong.example/token"},
        )
        token_route = mock.post(explicit).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        await client.get_access_token()
        assert discovery_route.call_count == 0  # explicit URL wins
        assert token_route.call_count == 1
        body = parse_qs(token_route.calls.last.request.content.decode())
        assert body["grant_type"] == ["password"]


@pytest.mark.asyncio
async def test_oauth_issuer_only_triggers_discovery(auth_token_response):
    issuer = "https://idp.example.com/realms/dev"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    discovered_token_url = "https://idp.example.com/realms/dev/protocol/openid-connect/token"
    client = GundiClient(
        oauth_issuer=issuer,
        oauth_client_id="public-client",
        username="alice",
        password="s3cret",
        base_url="https://api.fakeportal.com",
    )
    # Make sure no oauth_token_url leaked in from env:
    client.oauth_token_url = None
    async with respx.mock as mock:
        discovery_route = mock.get(discovery_url).respond(
            status_code=httpx.codes.OK,
            json={"issuer": issuer, "token_endpoint": discovered_token_url},
        )
        token_route = mock.post(discovered_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        await client.get_access_token()
        assert discovery_route.call_count == 1
        assert token_route.call_count == 1


@pytest.mark.asyncio
async def test_no_token_url_or_issuer_raises():
    client = GundiClient(
        oauth_client_id="public-client",
        username="alice",
        password="s3cret",
        base_url="https://api.fakeportal.com",
    )
    client.oauth_token_url = None
    client.oauth_issuer = None
    with pytest.raises(errors.AuthenticationError) as exc:
        await client.get_access_token()
    assert "token URL" in str(exc.value).lower() or "issuer" in str(exc.value).lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/client/test_oidc_discovery.py -v`
Expected: FAIL — `oauth_issuer` is not a recognized kwarg, and there's no `_resolve_token_url`; the client uses `self.oauth_token_url` directly so token requests go to `None`/derived URL.

- [ ] **Step 3: Add the `oauth_issuer` kwarg to `GundiClient.__init__`**

In `gundi_client_v2/client.py`, replace the auth-settings block in `GundiClient.__init__`. Find the existing lines starting `self.oauth_token_url = kwargs.get(...)` and insert the issuer right after them, so the block reads:

```python
        # Authentication settings
        # New oauth_* names preferred; keycloak_* still accepted for backward compatibility
        self.ssl_verify = kwargs.get("use_ssl", settings.GUNDI_API_SSL_VERIFY)
        self.client_id = kwargs.get("oauth_client_id",
                                    kwargs.get("keycloak_client_id", settings.OAUTH_CLIENT_ID))
        self.client_secret = kwargs.get("oauth_client_secret",
                                        kwargs.get("keycloak_client_secret", settings.OAUTH_CLIENT_SECRET))
        self.username = kwargs.get("username", settings.GUNDI_USERNAME)
        self.password = kwargs.get("password", settings.GUNDI_PASSWORD)
        self.oauth_token_url = kwargs.get("oauth_token_url", settings.OAUTH_TOKEN_URL)
        self.oauth_issuer = kwargs.get("oauth_issuer", settings.OAUTH_ISSUER)
        self.audience = kwargs.get("oauth_audience",
                                   kwargs.get("keycloak_audience", settings.OAUTH_AUDIENCE))
        self.scope = kwargs.get("oauth_scope", settings.OAUTH_SCOPE)
        self.cached_token = None
        self.cached_token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)
```

(The only new line is `self.oauth_issuer = ...`; everything else is unchanged.)

- [ ] **Step 4: Add `_resolve_token_url`**

In `gundi_client_v2/client.py`, add this method to `GundiClient` immediately above `_refresh_token`:

```python
    async def _resolve_token_url(self) -> str:
        """Return the token endpoint URL. Explicit oauth_token_url wins; otherwise
        discover it from oauth_issuer via OIDC discovery."""
        if self.oauth_token_url:
            return self.oauth_token_url
        if self.oauth_issuer:
            return await auth.discover_token_endpoint(self._session, self.oauth_issuer)
        raise errors.AuthenticationError(
            "No token URL configured. Set oauth_token_url or oauth_issuer."
        )
```

(Note: `_refresh_token` will be updated to call this in Task 7; for now it still uses `self.oauth_token_url` directly. The new tests pass because they configure `oauth_token_url` explicitly in one case, and the issuer-only test will exercise `_resolve_token_url` after Task 7 lands. To make the issuer-only test pass NOW, also update one call site — see Step 5.)

- [ ] **Step 5: Wire `_resolve_token_url` into the password-grant branch**

In `gundi_client_v2/client.py`, in `_refresh_token`, locate the password-grant branch (the `if self.username and self.password and self.client_id:` block). Replace it so the URL is resolved first:

Find:
```python
        # 2. Full authentication. Password grant wins when user credentials are present.
        # A client_id is required for every grant we support, so guard the password
        # branch on it too — otherwise we'd send a half-formed request and let the IdP
        # reject it remotely instead of failing locally with a clear configuration error.
        if self.username and self.password and self.client_id:
            logger.debug("Authenticating via password grant.")
            token = await auth.get_access_token_password_grant(
                session=self._session,
                oauth_token_url=self.oauth_token_url,
                client_id=self.client_id,
                username=self.username,
                password=self.password,
                audience=self.audience,
                scope=self.scope,
            )
```
Replace with:
```python
        # 2. Full authentication. Password grant wins when user credentials are present.
        # A client_id is required for every grant we support, so guard the password
        # branch on it too — otherwise we'd send a half-formed request and let the IdP
        # reject it remotely instead of failing locally with a clear configuration error.
        if self.username and self.password and self.client_id:
            logger.debug("Authenticating via password grant.")
            token_url = await self._resolve_token_url()
            token = await auth.get_access_token_password_grant(
                session=self._session,
                oauth_token_url=token_url,
                client_id=self.client_id,
                username=self.username,
                password=self.password,
                audience=self.audience,
                scope=self.scope,
            )
```

(The other branches still use `self.oauth_token_url` directly — Task 7 wires them up.)

- [ ] **Step 6: Run the tests**

Run: `./.venv/bin/python -m pytest tests/client/test_oidc_discovery.py -v && ./.venv/bin/python -m pytest -q`
Expected: discovery tests PASS (9 total in that file now); full suite PASS.

- [ ] **Step 7: Commit**

```bash
git add gundi_client_v2/client.py tests/client/test_oidc_discovery.py
git commit -m "feat: oauth_issuer kwarg + _resolve_token_url on GundiClient

GundiClient now accepts an oauth_issuer kwarg (settings.OAUTH_ISSUER fallback).
The new _resolve_token_url method returns the explicit oauth_token_url when
set, otherwise calls auth.discover_token_endpoint to find the token_endpoint
from the OIDC discovery document. The password-grant branch in _refresh_token
now goes through _resolve_token_url; other branches will be wired up in a
subsequent task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5 — `auth.get_access_token_client_credentials`

**Files:**
- Modify: `gundi_client_v2/auth.py`
- Create test entry in: `tests/client/test_password_grant.py` (or a new `test_client_credentials.py` — see note below)

> **Test placement note:** the existing confidential-mode flow is already exercised in `tests/client/test_password_grant.py` (e.g., `test_confidential_refresh_sends_client_secret`). Keep the new client_credentials tests there for proximity.

- [ ] **Step 1: Write the failing test**

Append to `tests/client/test_password_grant.py`:
```python
@pytest.mark.asyncio
async def test_client_credentials_payload(auth_token_response):
    client = _confidential_client()  # has oauth_client_id="confidential-client", oauth_client_secret="shhh"
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        await client.get_access_token()
        params = _body(route)
        assert params["grant_type"] == ["client_credentials"]
        assert params["client_id"] == ["confidential-client"]
        assert params["client_secret"] == ["shhh"]
        assert params["scope"] == ["openid"]


@pytest.mark.asyncio
async def test_client_credentials_audience_conditional(auth_token_response):
    client = _confidential_client(oauth_audience="my-portal")
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        await client.get_access_token()
        assert _body(route)["audience"] == ["my-portal"]

    client_no_aud = _confidential_client()
    client_no_aud.audience = None
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        await client_no_aud.get_access_token()
        assert "audience" not in _body(route)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/client/test_password_grant.py::test_client_credentials_payload -v`
Expected: FAIL — `_refresh_token` still calls `auth.get_access_token` (uma-ticket), so `grant_type` will be `urn:ietf:params:oauth:grant-type:uma-ticket`, not `client_credentials`. (Task 7 wires this up; for now we only need the new auth function to exist for the test to compile, but the assertion will fail.)

- [ ] **Step 3: Add `get_access_token_client_credentials` to `auth.py`**

In `gundi_client_v2/auth.py`, add this function immediately after `refresh_access_token`:

```python


async def get_access_token_client_credentials(
    session,
    oauth_token_url,
    client_id,
    client_secret,
    audience=None,
    scope="openid",
):
    """Standard OAuth2 client_credentials grant (RFC 6749 §4.4) for confidential clients.

    Responses for client_credentials typically do NOT include a refresh_token
    (RFC 6749 §4.4.3 says SHOULD NOT). We backfill empty values so the OAuthToken
    schema (which requires both fields) still parses; the client orchestrator
    treats the empty refresh_token + refresh_expires_in=0 as 'no refresh available'
    and re-authenticates on each access-token expiry.
    """
    logger.debug(f"get_access_token (client_credentials) from {oauth_token_url} using client_id: {client_id}")
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
        "scope": scope,
    }
    if audience:
        payload["audience"] = audience
    body = await _post_token(session, oauth_token_url, payload)
    body.setdefault("refresh_token", "")
    body.setdefault("refresh_expires_in", 0)
    return OAuthToken.parse_obj(body)
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest tests/client/test_password_grant.py::test_client_credentials_payload -v`
Expected: still FAIL — the new function exists, but `_refresh_token` doesn't call it yet. This is expected; Task 7 finishes the wiring. Do NOT proceed to Task 7 here — commit the auth.py addition by itself first so the diff is easy to review.

Run the full suite to confirm no regressions:
Run: `./.venv/bin/python -m pytest -q`
Expected: still PASSes everything that previously passed (the new function isn't called yet by production code).

- [ ] **Step 5: Commit**

```bash
git add gundi_client_v2/auth.py tests/client/test_password_grant.py
git commit -m "feat: add get_access_token_client_credentials (RFC 6749 §4.4)

Standard client_credentials grant for confidential clients. Backfills the
refresh_token/refresh_expires_in fields with empty/zero values because the
client_credentials response per spec SHOULD NOT include them, but the
OAuthToken schema (gundi-core) requires them on parse. The empty
refresh_token signals 'no refresh available' to _store_token, so the client
orchestrator naturally re-authenticates on each access-token expiry.

The tests added in this commit are not yet green; the call-site wiring
follows in a subsequent task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6 — `_store_token` handles refreshless tokens

**Files:**
- Modify: `gundi_client_v2/client.py` (only `_store_token`)
- Test: `tests/client/test_password_grant.py` (unit test on the helper)

- [ ] **Step 1: Write the failing test**

Append to `tests/client/test_password_grant.py`:
```python
from datetime import datetime, timezone
from gundi_core.schemas import OAuthToken


def test_store_token_refreshless_disables_refresh_tracking():
    # Synthesize a client_credentials-shape token: empty refresh_token, refresh_expires_in=0.
    client = _confidential_client()
    refreshless = OAuthToken.parse_obj({
        "access_token": "fresh-access",
        "expires_in": 1800,
        "refresh_token": "",
        "refresh_expires_in": 0,
        "token_type": "Bearer",
    })
    client._store_token(refreshless)
    assert client.cached_token.access_token == "fresh-access"
    assert client.cached_token_refresh_expires_at == datetime.min.replace(tzinfo=timezone.utc)
    # access-token expiry should still be set to a future moment via the buffer math
    assert client.cached_token_expires_at > datetime.now(tz=timezone.utc)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/client/test_password_grant.py::test_store_token_refreshless_disables_refresh_tracking -v`
Expected: FAIL — the current `_store_token` (when `refresh_rotated=True`, the default) unconditionally recomputes `cached_token_refresh_expires_at = now + _expiry_with_buffer(0)`, which is roughly `now`, not `datetime.min`.

- [ ] **Step 3: Update `_store_token`**

In `gundi_client_v2/client.py`, replace the `_store_token` method with:
```python
    def _store_token(self, token, *, refresh_rotated=True):
        # OAuthToken (gundi-core) always carries access + refresh fields on a successful parse,
        # but for grants that don't issue refresh tokens (e.g. client_credentials) the auth
        # helper backfills empty refresh_token and refresh_expires_in=0. Detect that here.
        # ``refresh_rotated`` is False only when this token came from a refresh-grant response
        # that omitted a new refresh_token (RFC 6749 §6) — in that case we preserve the
        # existing cached_token_refresh_expires_at because the cached refresh token is still
        # valid for its original lifetime.
        now = datetime.now(tz=timezone.utc)
        self.cached_token = token
        self.cached_token_expires_at = now + timedelta(
            seconds=self._expiry_with_buffer(token.expires_in)
        )
        if refresh_rotated:
            if token.refresh_token and token.refresh_expires_in > 0:
                self.cached_token_refresh_expires_at = now + timedelta(
                    seconds=self._expiry_with_buffer(token.refresh_expires_in)
                )
            else:
                # Refreshless grant — disable refresh tracking so the refresh-token
                # branch in _refresh_token doesn't pick this up.
                self.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest tests/client/test_password_grant.py -v && ./.venv/bin/python -m pytest -q`
Expected: new unit test PASSes; existing password-grant tests still PASS (they all use `auth_token_response`, which has `refresh_token` and `refresh_expires_in > 0`, so the new branch is not hit for them).

- [ ] **Step 5: Commit**

```bash
git add gundi_client_v2/client.py tests/client/test_password_grant.py
git commit -m "feat: _store_token disables refresh tracking for refreshless tokens

When a token has an empty refresh_token or refresh_expires_in == 0 (as
produced by the client_credentials helper's backfill), reset
cached_token_refresh_expires_at to datetime.min so the refresh-token branch
in _refresh_token is naturally skipped and the next access-token expiry
re-authenticates via the originating grant.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7 — Wire `client_credentials` into `_refresh_token`; drop uma-ticket

**Files:**
- Modify: `gundi_client_v2/auth.py` (remove uma-ticket flavor + constant)
- Modify: `gundi_client_v2/client.py` (`_refresh_token` confidential branch + use `_resolve_token_url` everywhere)

- [ ] **Step 1: Run the still-failing client_credentials tests as a baseline**

Run: `./.venv/bin/python -m pytest tests/client/test_password_grant.py::test_client_credentials_payload tests/client/test_password_grant.py::test_client_credentials_audience_conditional -v`
Expected: FAIL — confidential branch still calls `auth.get_access_token` (uma-ticket).

- [ ] **Step 2: Remove the uma-ticket flavor from `auth.py`**

In `gundi_client_v2/auth.py`, delete these two blocks:

```python
UMA_TICKET_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:uma-ticket"
```

and:

```python
async def get_access_token(session, oauth_token_url, client_id, client_secret, audience=None, scope="openid"):
    logger.debug(f"get_access_token from {oauth_token_url} using client_id: {client_id}")
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": UMA_TICKET_GRANT_TYPE,
        "scope": scope,
    }
    if audience:
        payload["audience"] = audience
    return await _token_request(session, oauth_token_url, payload)
```

(Make sure no other file imports `UMA_TICKET_GRANT_TYPE` or `get_access_token`. A repo-wide grep for both names should return zero hits after the removal.)

- [ ] **Step 3: Update `_refresh_token` confidential branch + resolve URL once at the top**

In `gundi_client_v2/client.py`, replace the entire `_refresh_token` method with:

```python
    async def _refresh_token(self):
        now = datetime.now(tz=timezone.utc)
        token_url = await self._resolve_token_url()

        # 1. Prefer the refresh-token grant when we hold a live refresh token.
        if (
            self.cached_token
            and self.cached_token.refresh_token
            and self.cached_token_refresh_expires_at > now
        ):
            try:
                token, refresh_rotated = await auth.refresh_access_token(
                    session=self._session,
                    oauth_token_url=token_url,
                    client_id=self.client_id,
                    refresh_token=self.cached_token.refresh_token,
                    fallback=self.cached_token,
                    # Public/password clients must not send a secret on refresh.
                    client_secret=None if (self.username and self.password) else self.client_secret,
                    scope=self.scope,
                )
                self._store_token(token, refresh_rotated=refresh_rotated)
                return token
            except errors.AuthenticationError:
                logger.info("Refresh-token grant failed; falling back to full re-authentication.")
                self.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)

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
        self._store_token(token)
        return token
```

(All three call sites now use `token_url` from `_resolve_token_url()`; the confidential branch calls `get_access_token_client_credentials` and the log line is updated.)

- [ ] **Step 4: Add an end-to-end test that proves the client_credentials wire-up**

Append to `tests/client/test_password_grant.py`:
```python
@pytest.mark.asyncio
async def test_confidential_refresh_after_client_credentials_falls_back_to_full_auth(auth_token_response):
    """A client_credentials initial response that lacks refresh_token must not be retried
    on the refresh-token path; the next force_refresh must re-authenticate."""
    # Token endpoint returns a client_credentials response shape: no refresh_token / no refresh_expires_in.
    client_credentials_response = {
        "access_token": "cc-access-token",
        "expires_in": auth_token_response["expires_in"],
        "token_type": "Bearer",
    }
    client = _confidential_client()
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=client_credentials_response
        )
        await client.get_access_token()                          # initial client_credentials
        await client.get_access_token(force_refresh_token=True)  # forced re-auth
        assert route.call_count == 2
        # Both calls must be client_credentials — refresh path was disabled by the empty refresh_token.
        assert _body(route, 0)["grant_type"] == ["client_credentials"]
        assert _body(route, 1)["grant_type"] == ["client_credentials"]
```

- [ ] **Step 5: Run the tests**

Run: `./.venv/bin/python -m pytest tests/client/test_password_grant.py -v && ./.venv/bin/python -m pytest -q`
Expected: ALL password-grant tests PASS (including the previously-failing `test_client_credentials_payload`, `test_client_credentials_audience_conditional`, and the new fall-back test); full suite PASS.

Note: the conftest fixture `client_settings` uses `keycloak_client_secret` (confidential mode). Existing tests in `test_connections.py`, `test_integrations.py`, etc. that hit the token endpoint will now send `grant_type=client_credentials` instead of `urn:...:uma-ticket`. None of those tests assert on `grant_type`, so they all still pass.

- [ ] **Step 6: Commit**

```bash
git add gundi_client_v2/auth.py gundi_client_v2/client.py tests/client/test_password_grant.py
git commit -m "feat: replace uma-ticket grant with client_credentials; resolve token URL lazily

The confidential-client branch in _refresh_token now sends
grant_type=client_credentials (RFC 6749 §4.4) — the standard for service-to-service
auth — instead of the Keycloak-specific uma-ticket grant. _refresh_token also
resolves the token URL once at the top via _resolve_token_url(), so the
issuer-only configuration path now works for every grant type.

Removed: auth.get_access_token (uma-ticket flavor) and UMA_TICKET_GRANT_TYPE.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8 — Version bump

**Files:**
- Modify: `gundi_client_v2/__init__.py`

- [ ] **Step 1: Bump the version**

In `gundi_client_v2/__init__.py`, change `__version__ = "2.5.0"` to `__version__ = "2.6.0"`. The file should read exactly:

```python
__version__ = "2.6.0"

from .client import GundiClient, GundiDataSenderClient
from .errors import GundiClientError, AuthenticationError, GundiAPIError
from . import errors
```

- [ ] **Step 2: Confirm**

Run: `./.venv/bin/python -c "import gundi_client_v2; print(gundi_client_v2.__version__)"`
Expected: `2.6.0`

- [ ] **Step 3: Commit**

```bash
git add gundi_client_v2/__init__.py
git commit -m "chore: bump version to 2.6.0

Public-surface additions (oauth_issuer kwarg) and a wire-level change
(confidential-client grant_type flips from uma-ticket to client_credentials)
warrant a minor bump.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9 — Documentation updates

**Files:**
- Modify: `README.md`
- Modify: `examples/.env.example` (if it references `OAUTH_ISSUER`/`OAUTH_TOKEN_URL`)
- Modify: `examples/send_observations.py` (only if it builds the token URL by Keycloak-shaped concat)

> The README on this branch was rewritten in PR #39 and patched in subsequent reviews; the current state lives at `cd/v2-docs`. This task corrects the parts that describe the now-removed Keycloak-derivation behavior and documents the new `oauth_issuer` kwarg + discovery flow.

- [ ] **Step 1: Update the env-vars table to reflect actual behavior**

In `README.md`, find the row for `OAUTH_ISSUER` (it currently says the token URL is derived as `{OAUTH_ISSUER}/protocol/openid-connect/token` with a trailing-slash note). Replace the row's description with:

```
| `OAUTH_ISSUER` | OIDC issuer URL. When set without `OAUTH_TOKEN_URL`, the token endpoint is discovered at runtime from `{OAUTH_ISSUER}/.well-known/openid-configuration`. A trailing slash is normalized. | — |
```

Also add a new row for `OAUTH_TOKEN_URL` directly above or below it:

```
| `OAUTH_TOKEN_URL` | Full OAuth token endpoint URL. When set, overrides OIDC discovery from `OAUTH_ISSUER`. | — |
```

- [ ] **Step 2: Update the kwargs table to add `oauth_issuer` and correct `oauth_token_url`**

In `README.md`, find the `GundiClient` kwargs table. Update the `oauth_token_url` row's "Corresponding env var" cell to `OAUTH_TOKEN_URL` (it was previously "— (derived from `OAUTH_ISSUER`)"; now both routes exist):

```
| `oauth_token_url` | `OAUTH_TOKEN_URL` | Full OAuth token endpoint URL. When set, used as-is. |
```

Add a row for `oauth_issuer`:

```
| `oauth_issuer` | `OAUTH_ISSUER` | OIDC issuer URL. When set without `oauth_token_url`, the token endpoint is discovered via OIDC discovery. |
```

- [ ] **Step 3: Replace the Authentication section's IdP-specific note**

In `README.md`, find the "Authentication" section, specifically the `> **Note:**` block about `keycloak_*` legacy names. Add a new short subsection just above that note titled `### Token URL resolution`:

```markdown
### Token URL resolution

The client resolves the OAuth token endpoint in this order:

1. **`oauth_token_url` (kwarg) / `OAUTH_TOKEN_URL` (env)** — used as-is when set.
2. **`oauth_issuer` (kwarg) / `OAUTH_ISSUER` (env)** — the client fetches `{issuer}/.well-known/openid-configuration` (OIDC discovery) and uses its `token_endpoint`. Result is cached for the process lifetime; call `gundi_client_v2.auth.clear_discovery_cache()` to invalidate.
3. **Neither set** — `AuthenticationError("No token URL configured.")` is raised on the first auth attempt.

OIDC discovery works for any compliant IdP (Keycloak, Auth0, Okta, …). Configure `OAUTH_ISSUER` and the token endpoint is found automatically.
```

- [ ] **Step 4: Update `examples/.env.example` and `examples/send_observations.py` if they encode the old derivation**

Check `examples/.env.example`. If it includes `OAUTH_ISSUER` as the recommended way to "derive" the URL, update the comment to reference OIDC discovery instead. Don't remove the variable — it's still the recommended config.

Check `examples/send_observations.py`. If the script reads `OAUTH_ISSUER` and synthesizes a token URL by string concatenation (the PR #39 review surfaced this), remove the local concatenation: just pass `oauth_issuer=os.environ.get("OAUTH_ISSUER")` (and `oauth_token_url` when set) to the `GundiClient` constructor and let discovery handle it.

If neither file needs changes, skip this step.

- [ ] **Step 5: Confirm the example file still parses**

Run: `./.venv/bin/python -c "import ast; ast.parse(open('examples/send_observations.py').read()); print('parses OK')"`
Expected: `parses OK`

- [ ] **Step 6: Run the full suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: full suite PASS (docs changes shouldn't affect it).

- [ ] **Step 7: Commit**

```bash
git add README.md examples/
git commit -m "docs: document OIDC discovery and the oauth_issuer kwarg

- README env-var and kwarg tables: OAUTH_TOKEN_URL now actually works as a
  direct env var; OAUTH_ISSUER now drives discovery (not a hardcoded derivation)
- New 'Token URL resolution' subsection documenting the explicit > discovered >
  error precedence
- examples/ updated to rely on the new client-level discovery instead of
  hand-concatenating a Keycloak-shaped token URL

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10 — Open the PR

- [ ] **Step 1: Push the branch**

```bash
git push -u origin cd/v2-oidc-discovery
```

- [ ] **Step 2: Open the PR against v2**

```bash
gh pr create --head cd/v2-oidc-discovery --base v2 \
  --title "feat: OIDC discovery + drop uma-ticket grant" \
  --body "$(cat <<'EOF'
## Summary
Replaces the Keycloak-specific token-URL derivation with OIDC discovery and replaces the uma-ticket grant with standard `grant_type=client_credentials`, so the library works against any OIDC-compliant IdP (Keycloak today, Auth0 next).

- New `auth.discover_token_endpoint(session, issuer)` fetches `{issuer}/.well-known/openid-configuration` and returns its `token_endpoint`. Process-lifetime cache keyed by `issuer.rstrip("/")`; `auth.clear_discovery_cache()` is the public escape hatch.
- New `oauth_issuer` kwarg on `GundiClient`; settings-layer `OAUTH_TOKEN_URL` is now a direct env var (not a derived value).
- New `auth.get_access_token_client_credentials` replaces the uma-ticket grant. Handles refreshless responses (RFC 6749 §4.4.3) by backfilling empty refresh fields and letting `_store_token` disable refresh tracking.
- `_store_token` recognizes refreshless tokens; `_refresh_token` resolves the token URL once at the top via `_resolve_token_url`.
- Backward compatibility preserved: existing `keycloak_*` kwargs, `KEYCLOAK_*` env fallbacks, and the module-level `KEYCLOAK_*` aliases all still work. Keycloak deployments using `OAUTH_ISSUER` keep working through discovery (Keycloak supports it natively).

Version bump to 2.6.0.

## Test Plan
- [x] `pytest` — full suite green
- [x] OIDC discovery: success, cached, trailing slash shares cache, 5xx → AuthenticationError, missing `token_endpoint` → AuthenticationError, `clear_discovery_cache()` invalidates
- [x] Token URL resolution: explicit `oauth_token_url` skips discovery; `oauth_issuer` only triggers discovery; neither set → AuthenticationError
- [x] `client_credentials`: payload shape; refreshless response → next call re-authenticates (no refresh-grant attempt)
- [x] Local smoke build: `uv build` produces a valid wheel + sdist

## Notes
- Stacks on `cd/v2-docs` (PR #39) for development; once #39 merges to v2 the base auto-retargets.
- Spec: `docs/superpowers/specs/2026-05-29-gundi-client-v2-oidc-discovery-design.md`
EOF
)"
```

- [ ] **Step 3: Confirm the PR exists**

```bash
gh pr view cd/v2-oidc-discovery --json url,number,baseRefName --jq '"PR #\(.number) (\(.url)) base=\(.baseRefName)"'
```
Expected: a single line confirming the PR number, URL, and that the base is `v2`.

---

## Self-review notes (author checklist — completed)

- **Spec coverage:**
  - Settings change → Task 2 ✓
  - Discovery function + cache + clear helper → Task 3 ✓
  - `oauth_issuer` kwarg + `_resolve_token_url` → Task 4 ✓
  - `client_credentials` grant → Task 5 ✓
  - `_store_token` refreshless handling → Task 6 ✓
  - `_refresh_token` rewire (drop uma-ticket; use `_resolve_token_url` everywhere) → Task 7 ✓
  - Conftest autouse fixture → Task 3 ✓
  - Version bump → Task 8 ✓
  - README + examples → Task 9 ✓
- **Placeholders:** none — every test and code step is concrete. The two judgement-driven steps (Task 9 step 4 about `examples/`) explicitly say "skip if not needed" so they aren't open-ended.
- **Type/name consistency:** `discover_token_endpoint`, `clear_discovery_cache`, `_DISCOVERY_CACHE`, `_resolve_token_url`, `oauth_issuer`, `get_access_token_client_credentials`, `_store_token(token, *, refresh_rotated=True)`, `cached_token_refresh_expires_at` are used uniformly across tasks. ✓
