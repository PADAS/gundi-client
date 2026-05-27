# gundi-client-v2 PR Split + OAuth2 Auth Refinement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Untangle the 4 bundled commits on `cd/add-password-grant-support` into 5 reviewable, concern-scoped, fully-tested PRs stacked on `origin/v2`, and refine authentication to comply with OAuth2 standards.

**Architecture:** Each PR is a topic branch cut from `origin/v2` (PRs 2–5 stack on the prior branch because they all touch `client.py`). Existing code on `cd/add-password-grant-support` is the reference for what the final files should contain, but each PR is **rebuilt by concern** with targeted edits — do not wholesale-copy `client.py` from the tangled branch, because it already contains later PRs' code. The auth refinement (refresh-token grant, OAuth error-body parsing, configurable scope, conditional audience) is **new** code not present anywhere yet; it lives in PR5.

**Tech Stack:** Python ≥3.10, httpx (async), pydantic v1/v2 via `gundi-core`, uv + hatchling (packaging), pytest + pytest-asyncio + respx (tests).

**Spec:** `docs/superpowers/specs/2026-05-27-gundi-client-v2-auth-refinement-design.md`

---

## Conventions for every PR

- Run tests with the project venv: `./.venv/bin/python -m pytest -q`
- Run a single test: `./.venv/bin/python -m pytest tests/client/test_auth.py::test_name -v`
- All token-endpoint and API interactions are **respx-mocked** (no live network).
- Commit messages use Conventional Commits. End commit bodies with:
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
- Stacking & rebasing: after a PR merges into `v2`, rebase the remaining open branches onto the updated `v2` (`git rebase --onto origin/v2 <old-base> <branch>`).

---

## Phase / PR 1 — `chore: migrate poetry → uv`

**Branch:** `git checkout -b cd/v2-uv origin/v2`

**Files:**
- Modify: `pyproject.toml` (poetry → hatchling/uv)
- Create: `uv.lock`
- Delete: `poetry.lock`
- Modify: `.gitignore` (add `.DS_Store`, `.vscode/`)

This PR has no application-logic tests — it is a build-system migration. Verification is "the package still imports and the existing suite passes under the new toolchain."

- [ ] **Step 1: Create the branch**

```bash
git fetch origin
git checkout -b cd/v2-uv origin/v2
```

- [ ] **Step 2: Replace `pyproject.toml` with the uv/hatchling version**

Write `pyproject.toml` to exactly this content:

```toml
[project]
name = "gundi-client-v2"
dynamic = ["version"]
description = "An async client for Gundi's API"
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.10"
authors = [
    { name = "Chris Doehring", email = "chrisdo@earthranger.com" },
    { name = "Mariano M", email = "marianom@earthranger.com" },
    { name = "Victor Garcia", email = "victorg@earthranger.com" },
]

dependencies = [
    "environs>=9.5,<12",
    "pydantic>=1.10,<3",
    "httpx>=0.28",
    "gundi-core>=1.5.8,<3",
]

[dependency-groups]
dev = [
    "respx>=0.22",
    "black>=23.1",
    "pytest>=7.2",
    "pytest-asyncio>=0.20",
]

[tool.hatch.version]
path = "gundi_client_v2/__init__.py"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 3: Delete `poetry.lock` and generate `uv.lock`**

```bash
git rm poetry.lock
uv lock
```

Expected: `uv.lock` created. If `uv` is unavailable, copy `uv.lock` from the reference branch: `git checkout cd/add-password-grant-support -- uv.lock`.

- [ ] **Step 4: Add editor/OS junk to `.gitignore`**

Append to `.gitignore`:

```gitignore
# OS / editor junk
.DS_Store
.vscode/
```

- [ ] **Step 5: Verify the package imports and the existing suite passes**

```bash
./.venv/bin/python -c "import gundi_client_v2; print(gundi_client_v2.__version__)"
./.venv/bin/python -m pytest -q
```

Expected: version prints (e.g. `2.4.1`); all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .gitignore
git commit -m "chore: migrate packaging from poetry to uv/hatchling

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase / PR 2 — `refactor: oauth_* kwargs + settings (keycloak_* compat)`

**Branch:** `git checkout -b cd/v2-oauth-rename cd/v2-uv`

**Files:**
- Modify: `gundi_client_v2/settings.py`
- Modify: `gundi_client_v2/client.py:150-161` (auth attrs) and `:206-226` (`_post`/`_get` 302 retry fix)
- Test: `tests/client/test_auth.py` (new)

Renames `keycloak_*` config to `oauth_*` with backward-compatible fallbacks, fixes the broken `_post` 302-retry (it referenced an undefined `json` and never reassigned the retried response), and makes `_get`'s retry merge caller headers consistently.

- [ ] **Step 1: Write the failing test**

Create `tests/client/test_auth.py`:

```python
import httpx
import pytest
import respx
from urllib.parse import parse_qs

from gundi_client_v2.client import GundiClient


def _token_body(route):
    return parse_qs(route.calls.last.request.content.decode())


@pytest.mark.asyncio
async def test_authenticates_with_oauth_kwargs(auth_token_response):
    client = GundiClient(
        oauth_token_url="https://fakeauth.com/realms/dev/protocol/openid-connect/token",
        oauth_client_id="confidential-client",
        oauth_client_secret="shhh",
        oauth_audience="my-portal",
        base_url="https://api.fakeportal.com",
    )
    async with respx.mock as mock:
        token_route = mock.post(client.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        header = await client.get_auth_header()
        assert header["authorization"].startswith("Bearer ")
        params = _token_body(token_route)
        assert params["grant_type"] == ["urn:ietf:params:oauth:grant-type:uma-ticket"]
        assert params["client_id"] == ["confidential-client"]
        assert params["client_secret"] == ["shhh"]


@pytest.mark.asyncio
async def test_keycloak_kwargs_backward_compatible():
    client = GundiClient(
        oauth_token_url="https://fakeauth.com/realms/dev/protocol/openid-connect/token",
        keycloak_client_id="legacy-client",
        keycloak_client_secret="legacy-secret",
        keycloak_audience="legacy-aud",
        base_url="https://api.fakeportal.com",
    )
    assert client.client_id == "legacy-client"
    assert client.client_secret == "legacy-secret"
    assert client.audience == "legacy-aud"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/client/test_auth.py -v`
Expected: FAIL — `GundiClient` still uses `keycloak_*` attrs / `settings.KEYCLOAK_*`, so `oauth_*` kwargs are ignored and `client.client_id` is `None` in the first test.

- [ ] **Step 3: Update `settings.py` to prefer OAUTH_* with KEYCLOAK_* fallback**

Replace the OAuth block in `gundi_client_v2/settings.py` (the `KEYCLOAK_ISSUER` … `KEYCLOAK_AUDIENCE` lines) with:

```python
# OAuth settings — OAUTH_* preferred; KEYCLOAK_* accepted for backward compatibility
OAUTH_ISSUER = env.str("OAUTH_ISSUER", env.str("KEYCLOAK_ISSUER", None))
OAUTH_TOKEN_URL = f"{OAUTH_ISSUER}/protocol/openid-connect/token" if OAUTH_ISSUER else None
OAUTH_CLIENT_ID = env.str("OAUTH_CLIENT_ID", env.str("KEYCLOAK_CLIENT_ID", None))
OAUTH_CLIENT_SECRET = env.str("OAUTH_CLIENT_SECRET", env.str("KEYCLOAK_CLIENT_SECRET", None))
OAUTH_AUDIENCE = env.str("OAUTH_AUDIENCE", env.str("KEYCLOAK_AUDIENCE", None))
```

(This also fixes a latent bug: the old `OAUTH_TOKEN_URL = f"{KEYCLOAK_ISSUER}/..."` produced the literal string `"None/protocol/..."` when the issuer was unset.)

- [ ] **Step 4: Update the auth attributes in `client.py`**

In `gundi_client_v2/client.py`, replace the `# Authentication settings` block inside `GundiClient.__init__` with:

```python
        # Authentication settings
        # New oauth_* names preferred; keycloak_* still accepted for backward compatibility
        self.ssl_verify = kwargs.get("use_ssl", settings.GUNDI_API_SSL_VERIFY)
        self.client_id = kwargs.get("oauth_client_id",
                                    kwargs.get("keycloak_client_id", settings.OAUTH_CLIENT_ID))
        self.client_secret = kwargs.get("oauth_client_secret",
                                        kwargs.get("keycloak_client_secret", settings.OAUTH_CLIENT_SECRET))
        self.oauth_token_url = kwargs.get("oauth_token_url", settings.OAUTH_TOKEN_URL)
        self.audience = kwargs.get("oauth_audience",
                                   kwargs.get("keycloak_audience", settings.OAUTH_AUDIENCE))
        self.cached_token = None
        self.cached_token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
```

- [ ] **Step 5: Fix the `_post` 302-retry bug and `_get` header merge**

In `gundi_client_v2/client.py`, replace the `_post` 302-retry block with (note `json=data` and the response reassignment):

```python
        # Force refresh the token and retry if we get redirected to the login page
        if response.status_code == 302 and "auth/realms" in response.headers.get("location", ""):
            auth_headers = await self.get_auth_header(force_refresh_token=True)
            response = await self._session.post(
                url,
                json=data,
                params=params,
                headers={**auth_headers, **headers},
                **kwargs,
            )
        return response
```

And in `_get`, replace the retry block so caller headers are preserved:

```python
        # Force refresh the token and retry if we get redirected to the login page
        if response.status_code == 302 and "auth/realms" in response.headers.get("location", ""):
            auth_headers = await self.get_auth_header(force_refresh_token=True)
            response = await self._session.get(
                url,
                params=params,
                headers={**auth_headers, **headers},
                **kwargs,
            )
        return response
```

- [ ] **Step 6: Run the new tests and the full suite**

Run: `./.venv/bin/python -m pytest tests/client/test_auth.py -v && ./.venv/bin/python -m pytest -q`
Expected: new tests PASS; existing suite still PASSES (conftest's `keycloak_*` fixture resolves via fallback).

- [ ] **Step 7: Commit**

```bash
git add gundi_client_v2/settings.py gundi_client_v2/client.py tests/client/test_auth.py
git commit -m "refactor: prefer oauth_* config with keycloak_* fallback; fix 302 retry

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase / PR 3 — `feat: errors module + _raise_for_status`

**Branch:** `git checkout -b cd/v2-errors cd/v2-oauth-rename`

**Files:**
- Modify: `gundi_client_v2/errors.py` (currently empty)
- Modify: `gundi_client_v2/__init__.py` (export errors)
- Modify: `gundi_client_v2/client.py` (add `_raise_for_status`; route all API calls through it; map `GundiDataSenderClient` post/patch errors)
- Test: `tests/client/test_errors.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/client/test_errors.py`:

```python
import httpx
import pytest
import respx

from gundi_client_v2 import errors
from gundi_client_v2.client import GundiDataSenderClient


@pytest.mark.asyncio
async def test_get_raises_gundi_api_error_on_4xx(auth_token_response, gundi_client_v2):
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        integration_id = "11115b4f-88cd-49c4-a723-0ddff1f580c4"
        url = f"{gundi_client_v2.integrations_endpoint}/{integration_id}/"
        mock.get(url).respond(status_code=404, json={"detail": "Not found"})
        with pytest.raises(errors.GundiAPIError) as exc:
            await gundi_client_v2.get_integration_details(integration_id)
        assert exc.value.status_code == 404
        assert "Not found" in exc.value.detail


@pytest.mark.asyncio
async def test_data_sender_post_raises_gundi_api_error(
    gundi_data_sender_client_v2, event_payload
):
    async with respx.mock as mock:
        url = f"{gundi_data_sender_client_v2.sensors_api_endpoint}/events/"
        mock.post(url).respond(status_code=500, json={"detail": "boom"})
        with pytest.raises(errors.GundiAPIError) as exc:
            await gundi_data_sender_client_v2.post_events(data=[event_payload])
        assert exc.value.status_code == 500
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/client/test_errors.py -v`
Expected: FAIL — `errors.py` is empty (`AttributeError: module ... has no attribute 'GundiAPIError'`), and the read methods still call bare `response.raise_for_status()` raising `httpx.HTTPStatusError`.

- [ ] **Step 3: Fill in `errors.py`**

Write `gundi_client_v2/errors.py`:

```python
class GundiClientError(Exception):
    """Base exception for the Gundi client."""


class AuthenticationError(GundiClientError):
    """Raised when OAuth token retrieval or authentication fails."""


class GundiAPIError(GundiClientError):
    """Raised when the Gundi API returns a non-2xx response."""

    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}" if detail else f"HTTP {status_code}")
```

- [ ] **Step 4: Export errors from the package**

Set `gundi_client_v2/__init__.py` to:

```python
__version__ = "2.5.0"

from .client import GundiClient, GundiDataSenderClient
from .errors import GundiClientError, AuthenticationError, GundiAPIError
from . import errors
```

- [ ] **Step 5: Add `_raise_for_status` and route all calls through it**

Add this static method to `GundiClient` (place it just above `get_connection_details`):

```python
    @staticmethod
    def _raise_for_status(response):
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise errors.GundiAPIError(
                status_code=e.response.status_code,
                detail=e.response.text,
            ) from e
```

In every `GundiClient` read/write method (`get_connection_details`, `get_route_details`, `get_integration_details`, `get_integration_api_key`, `get_traces`, `register_integration_type`), replace the lines:

```python
        # ToDo: Add custom exceptions to handle errors
        response.raise_for_status()
```

with:

```python
        self._raise_for_status(response)
```

In `GundiDataSenderClient._post_data` and `_update_data`, replace:

```python
        client_response.raise_for_status()
```

with:

```python
        try:
            client_response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise errors.GundiAPIError(
                status_code=e.response.status_code,
                detail=e.response.text,
            ) from e
```

- [ ] **Step 6: Run the new tests and the full suite**

Run: `./.venv/bin/python -m pytest tests/client/test_errors.py -v && ./.venv/bin/python -m pytest -q`
Expected: new tests PASS; full suite PASSES.

- [ ] **Step 7: Commit**

```bash
git add gundi_client_v2/errors.py gundi_client_v2/__init__.py gundi_client_v2/client.py tests/client/test_errors.py
git commit -m "feat: add errors module and route API responses through _raise_for_status

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase / PR 4 — `feat: get_connections / get_integrations`

**Branch:** `git checkout -b cd/v2-read-methods cd/v2-errors`

**Files:**
- Modify: `gundi_client_v2/client.py` (add `_parse_list_response`, `get_connections`, `get_integrations`)
- Modify: `gundi_client_v2/client.py` import line (already has `AsyncGenerator`? add if missing)
- Test: `tests/client/test_read_methods.py` (new)
- Docs: `README.md`, `examples/` (port from reference branch)

- [ ] **Step 1: Write the failing test**

Create `tests/client/test_read_methods.py`:

```python
import httpx
import pytest
import respx
from gundi_core.schemas.v2 import Connection, Integration

from gundi_client_v2.client import GundiClient


def _integration(idx):
    return {
        "id": f"338225f3-91f9-4fe1-b013-35322900000{idx}",
        "name": f"Integration {idx}",
        "base_url": "https://example.org",
        "enabled": True,
        "type": {"id": "45c66a61-71e4-4664-a7f2-30d465f87aa6", "name": "EarthRanger",
                 "value": "earth_ranger", "description": "", "actions": []},
        "owner": {"id": "e2d1b0fc-69fe-408b-afc5-7f54872730c0", "name": "Org", "description": ""},
        "configurations": [], "additional": {}, "default_route": None, "status": "healthy",
    }


@pytest.mark.asyncio
async def test_get_connections_parses_bare_list(auth_token_response, connection_details, gundi_client_v2):
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(status_code=httpx.codes.OK, json=auth_token_response)
        mock.get(f"{gundi_client_v2.connections_endpoint}/").respond(
            status_code=httpx.codes.OK, json=[connection_details]
        )
        result = await gundi_client_v2.get_connections()
        assert len(result) == 1
        assert isinstance(result[0], Connection)


@pytest.mark.asyncio
async def test_get_connections_parses_results_envelope(auth_token_response, connection_details, gundi_client_v2):
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(status_code=httpx.codes.OK, json=auth_token_response)
        mock.get(f"{gundi_client_v2.connections_endpoint}/").respond(
            status_code=httpx.codes.OK, json={"results": [connection_details], "next": None}
        )
        result = await gundi_client_v2.get_connections()
        assert len(result) == 1
        assert isinstance(result[0], Connection)


@pytest.mark.asyncio
async def test_get_integrations_follows_pagination(auth_token_response, gundi_client_v2):
    page2 = f"{gundi_client_v2.integrations_endpoint}/?cursor=abc"
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(status_code=httpx.codes.OK, json=auth_token_response)
        mock.get(f"{gundi_client_v2.integrations_endpoint}/").respond(
            status_code=httpx.codes.OK, json={"results": [_integration(1)], "next": page2}
        )
        mock.get(page2).respond(
            status_code=httpx.codes.OK, json={"results": [_integration(2)], "next": None}
        )
        collected = [i async for i in gundi_client_v2.get_integrations()]
        assert [i.name for i in collected] == ["Integration 1", "Integration 2"]
        assert all(isinstance(i, Integration) for i in collected)


@pytest.mark.asyncio
async def test_get_integrations_single_page_list(auth_token_response, gundi_client_v2):
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(status_code=httpx.codes.OK, json=auth_token_response)
        mock.get(f"{gundi_client_v2.integrations_endpoint}/").respond(
            status_code=httpx.codes.OK, json=[_integration(1)]
        )
        collected = [i async for i in gundi_client_v2.get_integrations()]
        assert len(collected) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/client/test_read_methods.py -v`
Expected: FAIL — `AttributeError: 'GundiClient' object has no attribute 'get_connections'`.

- [ ] **Step 3: Ensure `AsyncGenerator` is imported**

Confirm the typing import in `client.py` reads:

```python
from typing import AsyncGenerator, List
```

If it only imports `List`, add `AsyncGenerator`.

- [ ] **Step 4: Add the helper and methods**

Add `_parse_list_response` as a static method on `GundiClient` (just below `_raise_for_status`):

```python
    @staticmethod
    def _parse_list_response(data, model):
        if isinstance(data, list):
            return parse_obj_as(List[model], data)
        if isinstance(data, dict) and "results" in data:
            return parse_obj_as(List[model], data["results"])
        return [model.parse_obj(data)]
```

Add `get_connections` (just above `get_connection_details`):

```python
    async def get_connections(self, params: dict = None) -> List[Connection]:
        url = f"{self.connections_endpoint}/"
        response = await self._get(url, params=params)
        self._raise_for_status(response)
        return self._parse_list_response(response.json(), Connection)
```

Add `get_integrations` (just above `get_integration_details`):

```python
    async def get_integrations(self, params: dict = None) -> AsyncGenerator[Integration, None]:
        url = f"{self.integrations_endpoint}/"
        while url:
            response = await self._get(url, params=params)
            self._raise_for_status(response)
            data = response.json()
            params = None  # the `next` URL already carries the query string
            if isinstance(data, list):
                for item in parse_obj_as(List[Integration], data):
                    yield item
                return
            if isinstance(data, dict) and "results" in data:
                for item in parse_obj_as(List[Integration], data["results"]):
                    yield item
                url = data.get("next") or ""
                continue
            yield Integration.parse_obj(data)
            return
```

- [ ] **Step 5: Run the new tests and the full suite**

Run: `./.venv/bin/python -m pytest tests/client/test_read_methods.py -v && ./.venv/bin/python -m pytest -q`
Expected: new tests PASS; full suite PASSES.

- [ ] **Step 6: Port the docs for these methods**

```bash
git checkout cd/add-password-grant-support -- examples/
git checkout cd/add-password-grant-support -- README.md
```

Then review `README.md`: keep only the sections documenting `get_connections`/`get_integrations` and general client usage; **defer** any password-grant / auth sections to PR5 (remove them from this PR's README diff if present). If splitting the README is fiddly, leave auth docs out entirely here and add them in PR5.

- [ ] **Step 7: Commit**

```bash
git add gundi_client_v2/client.py tests/client/test_read_methods.py examples/ README.md
git commit -m "feat: add get_connections and paginated get_integrations

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase / PR 5 — `feat: password grant + OAuth2-compliant token/refresh`

**Branch:** `git checkout -b cd/v2-password-grant cd/v2-read-methods`

**Files:**
- Modify: `gundi_client_v2/settings.py` (add `GUNDI_USERNAME`, `GUNDI_PASSWORD`, `OAUTH_SCOPE`)
- Rewrite: `gundi_client_v2/auth.py` (add `_token_request`, `_extract_oauth_error`, `refresh_access_token`, `get_access_token_password_grant`; refine `get_access_token`)
- Modify: `gundi_client_v2/client.py` (`__init__` adds username/password/scope/refresh-expiry; rewrite `_refresh_token`; add `_store_token`)
- Test: `tests/client/test_password_grant.py` (new)
- Docs: `README.md` auth section

### Task 5.1 — settings

- [ ] **Step 1: Add settings**

In `gundi_client_v2/settings.py`, after the `OAUTH_AUDIENCE` line add:

```python
OAUTH_SCOPE = env.str("OAUTH_SCOPE", "openid")
```

And after the `SENSORS_API_BASE_URL` line add:

```python
GUNDI_USERNAME = env.str("GUNDI_USERNAME", None)
GUNDI_PASSWORD = env.str("GUNDI_PASSWORD", None)
```

### Task 5.2 — auth.py functions

- [ ] **Step 1: Write the failing test**

Create `tests/client/test_password_grant.py`:

```python
import httpx
import pytest
import respx
from urllib.parse import parse_qs

from gundi_client_v2 import errors
from gundi_client_v2.client import GundiClient

TOKEN_URL = "https://fakeauth.com/realms/dev/protocol/openid-connect/token"


def _public_password_client(**overrides):
    kwargs = dict(
        oauth_token_url=TOKEN_URL,
        oauth_client_id="public-client",
        username="alice",
        password="s3cret",
        base_url="https://api.fakeportal.com",
    )
    kwargs.update(overrides)
    client = GundiClient(**kwargs)
    # Defend against ambient env credentials leaking into assertions:
    if "oauth_client_secret" not in overrides:
        client.client_secret = None
    return client


def _confidential_client(**overrides):
    kwargs = dict(
        oauth_token_url=TOKEN_URL,
        oauth_client_id="confidential-client",
        oauth_client_secret="shhh",
        base_url="https://api.fakeportal.com",
    )
    kwargs.update(overrides)
    client = GundiClient(**kwargs)
    client.username = None
    client.password = None
    return client


def _body(route, index=-1):
    return parse_qs(route.calls[index].request.content.decode())


@pytest.mark.asyncio
async def test_password_grant_payload(auth_token_response):
    client = _public_password_client()
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        await client.get_access_token()
        params = _body(route)
        assert params["grant_type"] == ["password"]
        assert params["username"] == ["alice"]
        assert params["password"] == ["s3cret"]
        assert params["scope"] == ["openid"]
        assert "client_secret" not in params


@pytest.mark.asyncio
async def test_audience_omitted_when_unset(auth_token_response):
    client = _confidential_client()
    client.audience = None
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        await client.get_access_token()
        assert "audience" not in _body(route)


@pytest.mark.asyncio
async def test_audience_included_when_set(auth_token_response):
    client = _confidential_client(oauth_audience="my-portal")
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        await client.get_access_token()
        assert _body(route)["audience"] == ["my-portal"]


@pytest.mark.asyncio
async def test_scope_override(auth_token_response):
    client = _confidential_client(oauth_scope="openid profile")
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        await client.get_access_token()
        assert _body(route)["scope"] == ["openid profile"]


@pytest.mark.asyncio
async def test_error_body_surfaced(auth_token_response):
    client = _confidential_client()
    async with respx.mock as mock:
        mock.post(TOKEN_URL).respond(
            status_code=401,
            json={"error": "invalid_client", "error_description": "Invalid client credentials"},
        )
        with pytest.raises(errors.AuthenticationError) as exc:
            await client.get_access_token()
        assert "invalid_client" in str(exc.value)
        assert "Invalid client credentials" in str(exc.value)


@pytest.mark.asyncio
async def test_refresh_grant_used_and_password_not_resent(auth_token_response):
    client = _public_password_client()
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        await client.get_access_token()                      # initial: password grant
        await client.get_access_token(force_refresh_token=True)  # refresh grant
        assert route.call_count == 2
        assert _body(route, 0)["grant_type"] == ["password"]
        second = _body(route, 1)
        assert second["grant_type"] == ["refresh_token"]
        assert "refresh_token" in second
        assert "password" not in second
        assert "client_secret" not in second


@pytest.mark.asyncio
async def test_refresh_failure_falls_back_to_full_auth(auth_token_response):
    client = _public_password_client()
    async with respx.mock as mock:
        route = mock.post(TOKEN_URL)
        route.side_effect = [
            httpx.Response(httpx.codes.OK, json=auth_token_response),
            httpx.Response(400, json={"error": "invalid_grant", "error_description": "expired"}),
            httpx.Response(httpx.codes.OK, json=auth_token_response),
        ]
        await client.get_access_token()                       # call 0: password
        await client.get_access_token(force_refresh_token=True)  # call 1: refresh fails -> call 2: password
        assert route.call_count == 3
        assert _body(route, 1)["grant_type"] == ["refresh_token"]
        assert _body(route, 2)["grant_type"] == ["password"]


@pytest.mark.asyncio
async def test_no_credentials_raises():
    client = GundiClient(oauth_token_url=TOKEN_URL, base_url="https://api.fakeportal.com")
    client.client_id = None
    client.client_secret = None
    client.username = None
    client.password = None
    with pytest.raises(errors.AuthenticationError):
        await client.get_access_token()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/client/test_password_grant.py -v`
Expected: FAIL — `auth.get_access_token_password_grant` / `refresh_access_token` don't exist, `get_access_token` always sends `audience`, and `_refresh_token` has no refresh-grant path.

- [ ] **Step 3: Rewrite `auth.py`**

Write `gundi_client_v2/auth.py`:

```python
import logging

import httpx
from gundi_core.schemas import OAuthToken

from .errors import AuthenticationError

logger = logging.getLogger(__name__)

UMA_TICKET_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:uma-ticket"


def _extract_oauth_error(response):
    """Build a detail string from an RFC 6749 §5.2 token-error response."""
    status = response.status_code
    try:
        body = response.json()
    except ValueError:
        return f"Token request failed: HTTP {status}"
    error = body.get("error", "unknown_error")
    description = body.get("error_description")
    if description:
        return f"Token request failed: HTTP {status} ({error}: {description})"
    return f"Token request failed: HTTP {status} ({error})"


async def _token_request(session, oauth_token_url, payload) -> OAuthToken:
    response = await session.post(oauth_token_url, data=payload)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise AuthenticationError(_extract_oauth_error(e.response)) from e
    return OAuthToken.parse_obj(response.json())


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


async def get_access_token_password_grant(session, oauth_token_url, client_id, username, password, audience=None, scope="openid"):
    logger.debug(f"get_access_token (password grant) from {oauth_token_url} for user: {username}")
    payload = {
        "client_id": client_id,
        "username": username,
        "password": password,
        "grant_type": "password",
        "scope": scope,
    }
    if audience:
        payload["audience"] = audience
    return await _token_request(session, oauth_token_url, payload)


async def refresh_access_token(session, oauth_token_url, client_id, refresh_token, client_secret=None, scope="openid"):
    logger.debug(f"refresh_access_token from {oauth_token_url} using client_id: {client_id}")
    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": scope,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    return await _token_request(session, oauth_token_url, payload)
```

- [ ] **Step 4: Update `client.py` `__init__` auth block**

Replace the auth-settings block in `GundiClient.__init__` with (adds username/password/scope and a refresh-expiry tracker):

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
        self.audience = kwargs.get("oauth_audience",
                                   kwargs.get("keycloak_audience", settings.OAUTH_AUDIENCE))
        self.scope = kwargs.get("oauth_scope", settings.OAUTH_SCOPE)
        self.cached_token = None
        self.cached_token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)
```

- [ ] **Step 5: Rewrite `_refresh_token` and add `_store_token`**

Replace the existing `_refresh_token` method with:

```python
    async def _refresh_token(self):
        now = datetime.now(tz=timezone.utc)
        # 1. Prefer the refresh-token grant when we hold a live refresh token.
        if (
            self.cached_token
            and self.cached_token.refresh_token
            and self.cached_token_refresh_expires_at > now
        ):
            try:
                token = await auth.refresh_access_token(
                    session=self._session,
                    oauth_token_url=self.oauth_token_url,
                    client_id=self.client_id,
                    refresh_token=self.cached_token.refresh_token,
                    # Public/password clients must not send a secret on refresh.
                    client_secret=None if (self.username and self.password) else self.client_secret,
                    scope=self.scope,
                )
                self._store_token(token)
                return token
            except errors.AuthenticationError:
                logger.info("Refresh-token grant failed; falling back to full re-authentication.")

        # 2. Full authentication. Password grant wins when user credentials are present.
        if self.username and self.password:
            token = await auth.get_access_token_password_grant(
                session=self._session,
                oauth_token_url=self.oauth_token_url,
                client_id=self.client_id,
                username=self.username,
                password=self.password,
                audience=self.audience,
                scope=self.scope,
            )
        elif self.client_id and self.client_secret:
            token = await auth.get_access_token(
                session=self._session,
                oauth_token_url=self.oauth_token_url,
                client_id=self.client_id,
                client_secret=self.client_secret,
                audience=self.audience,
                scope=self.scope,
            )
        else:
            raise errors.AuthenticationError(
                "No credentials configured. Provide username/password or client_id/client_secret."
            )
        self._store_token(token)
        return token

    def _store_token(self, token):
        now = datetime.now(tz=timezone.utc)
        self.cached_token = token
        self.cached_token_expires_at = now + timedelta(seconds=token.expires_in - 15)  # skew buffer
        refresh_expires_in = getattr(token, "refresh_expires_in", None)
        if token.refresh_token and refresh_expires_in:
            self.cached_token_refresh_expires_at = now + timedelta(seconds=refresh_expires_in - 15)
        else:
            self.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)
```

Note: the old `_refresh_token` wrapped `auth.get_access_token` in a `try/except httpx.HTTPStatusError`. That mapping now lives in `auth._token_request` (raising `AuthenticationError`), so it is removed here.

- [ ] **Step 6: Run the new tests and the full suite**

Run: `./.venv/bin/python -m pytest tests/client/test_password_grant.py -v && ./.venv/bin/python -m pytest -q`
Expected: all password-grant tests PASS; full suite PASSES (the conftest confidential client still authenticates via uma-ticket grant; the redirect-retry test now exercises the refresh path and still succeeds against the mocked token endpoint).

- [ ] **Step 7: Add the auth docs to README**

Document password-grant usage (public client: `oauth_client_id` + `username` + `password`) and the `oauth_scope` option in `README.md`, mirroring the reference branch's auth section. Note in the README that password grant is for **public** clients only.

- [ ] **Step 8: Commit**

```bash
git add gundi_client_v2/settings.py gundi_client_v2/auth.py gundi_client_v2/client.py tests/client/test_password_grant.py README.md
git commit -m "feat: add OAuth2 password grant with refresh-token flow and error parsing

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after all 5 branches exist)

- [ ] **Run the whole suite on the top branch**

Run: `./.venv/bin/python -m pytest -q`
Expected: every test passes (existing 11 + new auth, errors, read-method, and password-grant tests).

- [ ] **Open the PRs in stacked order**

```bash
git push -u origin cd/v2-uv cd/v2-oauth-rename cd/v2-errors cd/v2-read-methods cd/v2-password-grant
```

Open each PR with base = the branch below it (PR1 base `v2`; PR2 base `cd/v2-uv`; …). As each merges into `v2`, rebase the remainder onto `v2`.

- [ ] **Clean up scratch artifacts (not part of any PR)**

These remain untracked in the working dir and should not be committed:
`.DS_Store`, `.cache_ggshield`, `.vscode/`, `licenses.txt`, `requirements.txt`, `testing.py`, `testit.py`.
`.DS_Store` and `.vscode/` are gitignored by PR1; remove the rest locally if undesired.

---

## Self-review notes (author checklist — completed)

- **Spec coverage:** PR1↔tooling §; PR2↔oauth rename §; PR3↔errors §; PR4↔read methods §; PR5↔password grant + all four OAuth2 refinements (refresh flow, error-body parsing, configurable scope, conditional audience) §. Credential precedence + refresh-fallback implemented in 5.5. ✓
- **Placeholders:** none — every code/test step contains full code; the only judgment call is README section-splitting (PR4 Step 6 / PR5 Step 7), which has explicit fallback instructions. ✓
- **Type/name consistency:** `_token_request`, `_extract_oauth_error`, `refresh_access_token`, `get_access_token_password_grant`, `_store_token`, `_raise_for_status`, `_parse_list_response`, `cached_token_refresh_expires_at`, `OAUTH_SCOPE`/`self.scope` used consistently across tasks. ✓
