# gundi-client-v2 docs site — Phase 1 implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a MkDocs Material documentation site for `gundi-client-v2` on GitHub Pages, with content covering installation, authentication, and reading Connections/Integrations.

**Architecture:** Static site built from markdown in `docs/`, configured via `mkdocs.yml` at repo root. Deployed by a GitHub Actions workflow that pushes to the `gh-pages` branch on every push to `v2`. Auto-generated API reference is **out of scope for this phase** (Phase 2).

**Tech Stack:** MkDocs 1.6+, mkdocs-material 9.5+, mkdocs-exclude, pymdownx extensions, GitHub Actions, GitHub Pages.

**Spec:** [`docs/superpowers/specs/2026-06-01-gundi-client-v2-docs-site-design.md`](../specs/2026-06-01-gundi-client-v2-docs-site-design.md)

---

## File map

| Path | Purpose |
|---|---|
| `pyproject.toml` | Add `[project.optional-dependencies] docs` group so `pip install -e ".[docs]"` works in CI and locally |
| `mkdocs.yml` | Site config: theme, plugins, nav, markdown extensions |
| `.github/workflows/docs.yml` | Build + deploy workflow, triggers on push to `v2` |
| `docs/index.md` | Landing page |
| `docs/getting-started/install.md` | Installation instructions |
| `docs/getting-started/auth-setup.md` | Auth env vars + obtaining a client/credentials |
| `docs/getting-started/first-request.md` | Smoke-test example: list Connections |
| `docs/concepts/data-model.md` | Gundi data model: Integrations, Connections, Routes, Providers/Destinations |
| `docs/authentication/overview.md` | Three auth paths at a glance |
| `docs/authentication/client-credentials.md` | M2M grant detail |
| `docs/authentication/password-grant.md` | User-facing ROPC grant |
| `docs/authentication/oidc-discovery.md` | Issuer-based discovery |
| `docs/authentication/refresh-and-errors.md` | Refresh token rotation, common auth errors |
| `docs/reading-data/connections.md` | `get_connections`, filtering, pagination |
| `docs/reading-data/integrations.md` | `get_integrations`, `get_integration_details`, `get_integration_api_key` |
| `docs/migration.md` | Renders `MIGRATION.md` via pymdownx snippets |
| `docs/troubleshooting.md` | Common auth + httpx errors |
| `docs/changelog.md` | Points readers to GitHub Releases |

---

## Task 1: Add docs dependency group

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read current `pyproject.toml` to confirm shape**

```bash
cat pyproject.toml
```

Expected: the file has a `dependencies` array under `[project]` and a `[dependency-groups]` table with a `dev` array. There is **no** `[project.optional-dependencies]` section yet.

- [ ] **Step 2: Add `[project.optional-dependencies]` with a `docs` group**

Insert after the `dependencies = [...]` block (before `[dependency-groups]`):

```toml
[project.optional-dependencies]
docs = [
    "mkdocs-material>=9.5",
    "mkdocs-exclude>=1.0",
]
```

- [ ] **Step 3: Verify the install works**

```bash
uv pip install -e ".[docs]"
mkdocs --version
```

Expected: `mkdocs, version 1.x.x` printed. No errors.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "docs: add [docs] optional-dependency group for the site build"
```

---

## Task 2: Add the MkDocs configuration

**Files:**
- Create: `mkdocs.yml`

- [ ] **Step 1: Create `mkdocs.yml` at the repo root**

```yaml
site_name: gundi-client-v2 (Python)
site_description: Async Python client for the Gundi platform API
site_url: https://padas.github.io/gundi-client/
repo_url: https://github.com/PADAS/gundi-client
repo_name: PADAS/gundi-client
edit_uri: edit/v2/docs/

theme:
  name: material
  features:
    - navigation.tabs
    - navigation.sections
    - navigation.expand
    - navigation.path
    - navigation.top
    - search.suggest
    - search.highlight
    - content.code.copy
    - content.code.annotate
    - content.action.edit
    - toc.follow
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      primary: teal
      accent: teal
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      primary: teal
      accent: teal
      toggle:
        icon: material/brightness-4
        name: Switch to light mode

plugins:
  - search
  - exclude:
      glob:
        - "superpowers/**"

markdown_extensions:
  - admonition
  - attr_list
  - md_in_html
  - tables
  - toc:
      permalink: true
  - pymdownx.details
  - pymdownx.tabbed:
      alternate_style: true
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.inlinehilite
  - pymdownx.snippets:
      base_path: ["."]
  - pymdownx.superfences
  - pymdownx.emoji:
      emoji_index: !!python/name:material.extensions.emoji.twemoji
      emoji_generator: !!python/name:material.extensions.emoji.to_svg

nav:
  - Home: index.md
  - Getting started:
    - Installation: getting-started/install.md
    - Authentication setup: getting-started/auth-setup.md
    - First request: getting-started/first-request.md
  - Concepts:
    - Gundi data model: concepts/data-model.md
  - Authentication:
    - Overview: authentication/overview.md
    - Client credentials: authentication/client-credentials.md
    - Password grant: authentication/password-grant.md
    - OIDC discovery: authentication/oidc-discovery.md
    - Refresh and errors: authentication/refresh-and-errors.md
  - Reading data:
    - Connections: reading-data/connections.md
    - Integrations: reading-data/integrations.md
  - Migration (2.x → 3.0): migration.md
  - Troubleshooting: troubleshooting.md
  - Changelog: changelog.md
```

- [ ] **Step 2: Confirm `mkdocs.yml` parses by running build with `--strict`**

```bash
mkdocs build --strict
```

Expected: build fails with errors like `'docs/index.md' not found` — the nav references files that don't exist yet. **That's expected** and validates that `mkdocs.yml` itself is syntactically valid.

- [ ] **Step 3: Commit**

```bash
git add mkdocs.yml
git commit -m "docs: add mkdocs.yml with Material theme and Phase 1 nav"
```

---

## Task 3: Add the GitHub Actions workflow for docs deploy

**Files:**
- Create: `.github/workflows/docs.yml`

- [ ] **Step 1: Create the workflow file**

```yaml
name: docs

on:
  push:
    branches: [v2]
    paths:
      - docs/**
      - mkdocs.yml
      - pyproject.toml
      - .github/workflows/docs.yml
  workflow_dispatch:

permissions:
  contents: write

# Serialize deploys so two pushes to v2 in quick succession don't race
# on gh-deploy --force.
concurrency:
  group: docs-deploy
  cancel-in-progress: false

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          # gh-deploy needs full history to commit to gh-pages.
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install docs dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[docs]"

      # --strict catches broken internal links and missing nav targets.
      - name: Build site
        run: mkdocs build --strict

      - name: Deploy to gh-pages
        run: mkdocs gh-deploy --force
```

- [ ] **Step 2: Commit (no remote deploy yet — gh-pages branch doesn't exist; first push to v2 will create it)**

```bash
git add .github/workflows/docs.yml
git commit -m "docs: add GitHub Actions workflow to build and deploy to gh-pages"
```

---

## Task 4: Write `docs/index.md` (Home)

**Files:**
- Create: `docs/index.md`

- [ ] **Step 1: Write the page**

```markdown
# gundi-client-v2

**An async Python client for the [Gundi](https://gundiservice.org) platform.**

Use this library to authenticate against Gundi, read Integrations and
Connections in your account, send Observations and Events, and manage Routes
— from any Python 3.10+ application.

## Who this is for

Python developers building third-party apps or utilities that interact with
Gundi. You should be comfortable with async Python (`asyncio`, `await`) and
basic HTTP-API concepts. You do **not** need prior experience with Gundi,
Keycloak, or OAuth2 — this documentation walks you through it.

If you're new to Gundi as a platform, start at
[gundiservice.org](https://gundiservice.org) instead.

## What's inside

- **Async-first** — all I/O methods are coroutines; use the client as an
  async context manager.
- **Three OAuth2 auth paths** — `client_credentials` (M2M),
  `password` (user-facing), or **OIDC discovery** against any compliant IdP.
- **Pydantic-modeled responses** — Connections, Integrations, Routes, and
  Traces parse into typed objects defined in
  [`gundi-core`](https://pypi.org/project/gundi-core/).
- **`GundiClient`** for portal/configuration API calls.
- **`GundiDataSenderClient`** for sending observations and events using an
  Integration API key.

## Start here

- **First time?** → [Installation](getting-started/install.md) →
  [Authentication setup](getting-started/auth-setup.md) →
  [First request](getting-started/first-request.md)
- **Need a refresher on the data model?** →
  [Gundi data model](concepts/data-model.md)
- **Migrating from 2.x?** → [Migration guide](migration.md)
- **Hitting an error?** → [Troubleshooting](troubleshooting.md)

## How this site is organized

| Section | What's there |
|---|---|
| **Getting started** | Install, set up credentials, make your first request |
| **Concepts** | Background on Gundi's data model |
| **Authentication** | Detailed coverage of the three OAuth2 flows |
| **Reading data** | How to fetch Connections and Integrations |
| **Migration** | 2.x → 3.0 upgrade guide |
| **Troubleshooting** | Common errors and fixes |
```

- [ ] **Step 2: Verify the build progresses past the index file**

```bash
mkdocs build --strict 2>&1 | head -10
```

Expected: errors about missing pages still exist (other nav entries), but no error mentions `index.md`.

- [ ] **Step 3: Commit**

```bash
git add docs/index.md
git commit -m "docs: add Home page (index.md)"
```

---

## Task 5: Write `docs/getting-started/install.md`

**Files:**
- Create: `docs/getting-started/install.md`

- [ ] **Step 1: Write the page**

```markdown
# Installation

## Prerequisites

- **Python 3.10 or newer.** Check with `python3 --version`.
- A package installer — `pip` or `uv` (recommended for speed).

## Install from PyPI

```bash
uv pip install gundi-client-v2
```

Or with plain pip:

```bash
pip install gundi-client-v2
```

Pin to a specific version with `gundi-client-v2==X.Y.Z`. The latest release
is on the [PyPI project page](https://pypi.org/project/gundi-client-v2/).

## Install from source

For development or to pin to a specific commit:

```bash
pip install "gundi-client-v2 @ git+https://github.com/PADAS/gundi-client.git@v2"
```

## Compatibility

| Package | Required |
|---|---|
| Python | `>=3.10` |
| `httpx` | `>=0.28` |
| `pydantic` | `>=1.10,<2` (pydantic v1 line) |
| `gundi-core` | `>=1.5.8,<3` |

If your app uses **FastAPI**, you'll also need `fastapi>=0.110.3` and
`starlette>=0.37` to coexist with `httpx>=0.28`. See the
[Migration guide](../migration.md) for details on the upgrade triangle.

## Verify

After installing, confirm the import succeeds:

```bash
python -c "import gundi_client_v2; print(gundi_client_v2.__version__)"
```

Expected output: the installed version number (e.g. `3.0.0`).

## Next

→ [Authentication setup](auth-setup.md) — configure credentials so the
client can talk to Gundi.
```

- [ ] **Step 2: Commit**

```bash
git add docs/getting-started/install.md
git commit -m "docs: add Installation page"
```

---

## Task 6: Write `docs/getting-started/auth-setup.md`

**Files:**
- Create: `docs/getting-started/auth-setup.md`

- [ ] **Step 1: Write the page**

```markdown
# Authentication setup

`gundi-client-v2` reads its OAuth2 configuration from environment variables
by default. This page covers the **happy path** for most users; for
detailed coverage of each grant type, see the
[Authentication section](../authentication/overview.md).

## What you need from your Gundi administrator

- The **API base URL** for your Gundi deployment (e.g.
  `https://api.gundiservice.org`).
- An **OAuth issuer URL** for the IdP behind Gundi
  (e.g. `https://auth.gundiservice.org/realms/your-realm`).
- An **OAuth client** (ID, and a secret if it's a confidential client).
- Either user credentials (for password grant) **or** a client secret
  (for client_credentials).

## Choose a grant type

| Use this | When |
|---|---|
| `client_credentials` | Server-to-server, no user identity involved. Your client is confidential (has a secret). |
| `password` | Acting on behalf of a known user with their credentials. Your client is public (no secret). |

If unsure, ask your Gundi administrator which grant your client is configured
for.

## Set the environment variables

Create a `.env` file next to your application code, or export these in your
shell:

=== "client_credentials"

    ```env
    GUNDI_API_BASE_URL=https://api.gundiservice.org
    OAUTH_ISSUER=https://auth.gundiservice.org/realms/your-realm
    OAUTH_CLIENT_ID=your-client-id
    OAUTH_CLIENT_SECRET=your-client-secret
    # OAUTH_AUDIENCE=your-api-audience   # required by some IdPs (e.g. Auth0)
    ```

=== "password grant"

    ```env
    GUNDI_API_BASE_URL=https://api.gundiservice.org
    OAUTH_ISSUER=https://auth.gundiservice.org/realms/your-realm
    OAUTH_CLIENT_ID=your-client-id
    GUNDI_USERNAME=your-username
    GUNDI_PASSWORD=your-password
    # OAUTH_AUDIENCE=your-api-audience   # required by some IdPs (e.g. Auth0)
    ```

## How the library uses these

When you create a `GundiClient()` with no arguments, it reads these env vars
through `gundi_client_v2.settings`. Setting `OAUTH_ISSUER` triggers **OIDC
discovery**: the library fetches the IdP's
`/.well-known/openid-configuration` document on the first auth attempt and
caches the resolved token endpoint for the process lifetime.

If your IdP doesn't expose discovery, set `OAUTH_TOKEN_URL` directly instead
of `OAUTH_ISSUER`.

!!! tip "Audience parameter"
    `OAUTH_AUDIENCE` is required by some IdPs (notably Auth0 won't issue a
    usable API access token without it) and ignored by others (Keycloak
    password grant). Set it if your IdP requires it; leave it unset
    otherwise.

## Loading the `.env` file

The library calls `environs.Env.read_env()` at import time. By default this
reads `./.env` from the current working directory. Run your script from the
directory containing `.env`, or set `GUNDI_CLIENT_ENVFILE=/path/to/your.env`
to point at a specific file.

## Next

→ [First request](first-request.md) — list the Connections in your account
to verify everything works.
```

- [ ] **Step 2: Commit**

```bash
git add docs/getting-started/auth-setup.md
git commit -m "docs: add Authentication setup page"
```

---

## Task 7: Write `docs/getting-started/first-request.md`

**Files:**
- Create: `docs/getting-started/first-request.md`

- [ ] **Step 1: Write the page**

```markdown
# First request

This page walks through a minimal end-to-end example: authenticate and list
the Connections in your Gundi account. If you haven't yet set environment
variables, do [Authentication setup](auth-setup.md) first.

## Smoke test

Save this as `smoke.py` in the same directory as your `.env`:

```python
import asyncio
import json
from gundi_client_v2 import GundiClient


async def main():
    async with GundiClient() as client:
        connections = await client.get_connections()
        print(f"Found {len(connections)} connections")
        if connections:
            # Print the first one as JSON
            print(json.dumps(connections[0].dict(), default=str, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
```

Run it:

```bash
python smoke.py
```

You should see a connection count and a JSON dump of the first Connection.

## What just happened

1. **`GundiClient()`** read your env vars (`GUNDI_API_BASE_URL`,
   `OAUTH_ISSUER`, and the credentials) into a configured client.
2. **`async with`** entered the client's async context. The first network
   call triggers OIDC discovery (fetch
   `{OAUTH_ISSUER}/.well-known/openid-configuration`) and obtains an
   access token.
3. **`client.get_connections()`** GETs `/v2/connections/` on your
   Gundi API, parses the response into `Connection` Pydantic models, and
   returns them as a list.
4. **Exiting the context** closes the underlying HTTPX session cleanly.

## Filtering and pagination

`get_connections()` accepts a `params` dict that's passed straight to the
API as query-string parameters:

```python
healthy = await client.get_connections(params={"status": "healthy"})
```

For full filter coverage and pagination patterns, see
[Reading data → Connections](../reading-data/connections.md).

## Next

- Learn how Gundi models its data → [Gundi data model](../concepts/data-model.md)
- Dive into the auth grants → [Authentication overview](../authentication/overview.md)
- See more `Connection` examples → [Reading Connections](../reading-data/connections.md)
```

- [ ] **Step 2: Commit**

```bash
git add docs/getting-started/first-request.md
git commit -m "docs: add First request page"
```

---

## Task 8: Write `docs/concepts/data-model.md`

**Files:**
- Create: `docs/concepts/data-model.md`

- [ ] **Step 1: Write the page**

```markdown
# Gundi data model

Gundi sits between **data providers** (devices, third-party APIs, telemetry
sources) and **destinations** (EarthRanger sites, SMART deployments, etc.).
Five resource types make up the platform:

```
Integration ──┐
              ├─► Connection ──► Route ──► Integration (destination)
Integration ──┘
```

## Integration

A registered third-party system that either **provides** data to Gundi or
**receives** data from it. Defined by an `IntegrationType` (e.g.
`er_traptagger`, `lotek`, `earthranger`) and an `IntegrationConfiguration`
that holds the system-specific settings (base URL, API key, etc.).

**You read these with:** [`get_integrations()`](../reading-data/integrations.md),
`get_integration_details(integration_id)`.

## Connection

A logical grouping of one or more provider Integrations that share a common
destination. A "TrapTagger camera trap network at Park X" might be a single
Connection containing several provider Integrations (each camera) routed to
one EarthRanger destination.

A Connection's primary fields:

- `provider` — the Integration that produces data
- `destinations` — list of Integrations that receive routed data
- `status` — `healthy`, `unhealthy`, `disabled`
- `routing_rules` — references to the Routes that direct the data

**You read these with:** [`get_connections()`](../reading-data/connections.md),
`get_connection_details(integration_id)`.

## Route

A rule that maps **provider** Integrations to **destination** Integrations,
with optional field-level transforms (often a JQ filter). Routes belong to an
**owner** Organization. A Connection's `routing_rules` are the Route IDs that
apply to it.

**You read these with:** `get_routes()`, `get_route_details(route_id)`,
`get_routes_for_connection(connection_id)`.
**You manage these with:** `create_route()`, `update_route()`, `delete_route()`.

## Observation, Event, Message

The three payload types Gundi forwards:

| Type | What it is | Sent with |
|---|---|---|
| **Observation** | A geolocated point (lat, lon, time, optional attributes) | `GundiDataSenderClient.post_observations` |
| **Event** | A discrete incident or record (type, time, location, attributes) | `GundiDataSenderClient.post_events` |
| **Message** | A text message (often paired with an Event or Observation) | `GundiDataSenderClient.post_messages` |

## Trace

A record of one payload's journey through Gundi: the source observation/event,
which Connection routed it, which destination(s) received it, and the
delivery outcome. Useful for diagnostics.

**You read these with:** `get_traces(params={...})`.

## How they fit together

A typical "provider → destination" flow:

1. A device pushes an Observation to Gundi via a provider Integration's
   webhook endpoint.
2. Gundi looks up the Connections containing that provider Integration.
3. For each matching Connection, Gundi consults its Routes to determine
   which destination Integrations should receive the data.
4. Gundi transforms the payload per the Route's `transformation_rules` if
   any, then forwards it to each destination.
5. A Trace is recorded for each provider → destination edge in the flow.
```

- [ ] **Step 2: Commit**

```bash
git add docs/concepts/data-model.md
git commit -m "docs: add Gundi data model concepts page"
```

---

## Task 9: Write `docs/authentication/overview.md`

**Files:**
- Create: `docs/authentication/overview.md`

- [ ] **Step 1: Write the page**

```markdown
# Authentication overview

`gundi-client-v2` supports three OAuth2 authentication paths. All three end
the same way — the client holds an access token and attaches it to every
outgoing request — but they differ in how that token is obtained.

## The three paths

| Path | Grant | When | Client type |
|---|---|---|---|
| [Client credentials](client-credentials.md) | `grant_type=client_credentials` (RFC 6749 §4.4) | Server-to-server, no user identity | **Confidential** (has a secret) |
| [Password grant](password-grant.md) | `grant_type=password` (ROPC; RFC 6749 §4.3) | Acting on behalf of a specific user | **Public** (no secret) |
| [OIDC discovery](oidc-discovery.md) | Either of the above, with token endpoint discovered automatically | Any IdP that supports OIDC Discovery 1.0 | Either |

OIDC discovery is **not a separate grant type** — it's a mechanism for the
library to discover the IdP's token endpoint at runtime from
`{OAUTH_ISSUER}/.well-known/openid-configuration`. You combine it with one of
the other two grants.

## How the client picks a grant

When you call any method on `GundiClient` that requires authentication, it
chooses a grant in this priority order:

1. If a **non-expired refresh token** is cached → refresh-token grant
   (RFC 6749 §6).
2. If `username` + `password` were provided → password grant.
3. If `client_secret` was provided → client_credentials grant.
4. Otherwise → `AuthenticationError`.

You don't normally call the grant functions directly; the client handles it.
But the standalone functions in `gundi_client_v2.auth` are available if you
need fine-grained control:

```python
from gundi_client_v2.auth import (
    get_access_token_client_credentials,
    get_access_token_password_grant,
    refresh_access_token,
    discover_token_endpoint,
)
```

## Resolving the token endpoint

The library needs to know **where** to POST the token request. Two ways to
configure this, in priority order:

1. **`OAUTH_TOKEN_URL`** (or the `oauth_token_url` kwarg) — set this
   directly to a fully-qualified URL like
   `https://auth.example.com/realms/myrealm/protocol/openid-connect/token`.
2. **`OAUTH_ISSUER`** (or the `oauth_issuer` kwarg) — set this to the
   issuer base URL; the library performs OIDC discovery to resolve the token
   endpoint. The result is cached for the process lifetime; call
   `auth.clear_discovery_cache()` to invalidate.

If neither is set, the client raises `AuthenticationError`.

## Errors you might see

| Error | Likely cause |
|---|---|
| `AuthenticationError: Token request failed: HTTP 401 (invalid_client)` | Wrong client ID or secret |
| `AuthenticationError: Token request failed: HTTP 401 (invalid_grant)` | Wrong username/password, or a revoked refresh token |
| `AuthenticationError: OIDC discovery failed for ...` | Issuer URL unreachable or doesn't expose `.well-known/openid-configuration` |
| `AuthenticationError: ...returned issuer ... does not match the expected issuer` | The discovery doc's `issuer` claim doesn't match the URL you used to fetch it — possible misconfiguration or man-in-the-middle |

Full details on each, with mitigation steps:
[Refresh and errors](refresh-and-errors.md).

## See also

- [Client credentials](client-credentials.md) — confidential clients, M2M flows
- [Password grant](password-grant.md) — user-facing flows
- [OIDC discovery](oidc-discovery.md) — IdP-agnostic token endpoint resolution
- [Refresh and errors](refresh-and-errors.md) — refresh token rotation, error scenarios
```

- [ ] **Step 2: Commit**

```bash
git add docs/authentication/overview.md
git commit -m "docs: add Authentication overview page"
```

---

## Task 10: Write `docs/authentication/client-credentials.md`

**Files:**
- Create: `docs/authentication/client-credentials.md`

- [ ] **Step 1: Write the page**

```markdown
# Client credentials grant

The `client_credentials` grant (RFC 6749 §4.4) is the standard OAuth2 flow
for **server-to-server** authentication. There is no user identity involved
— your service authenticates as itself using a client ID and secret.

## When to use it

- Your service is a confidential client (the secret can be kept private).
- The actions you perform are not tied to a specific user.
- Common use: batch jobs, schedulers, integrations that act as a system
  account.

## Environment variables

```env
GUNDI_API_BASE_URL=https://api.gundiservice.org
OAUTH_ISSUER=https://auth.gundiservice.org/realms/your-realm
OAUTH_CLIENT_ID=your-client-id
OAUTH_CLIENT_SECRET=your-client-secret
# OAUTH_AUDIENCE=your-api-audience   # required by some IdPs (e.g. Auth0)
```

## Minimal example

```python
import asyncio
from gundi_client_v2 import GundiClient


async def main():
    async with GundiClient() as client:
        connections = await client.get_connections()
        print(f"{len(connections)} connections accessible to this client")


asyncio.run(main())
```

The client reads the env vars at construction time. The first request
triggers an initial `client_credentials` token request; subsequent requests
reuse the cached token until it expires.

## What's on the wire

The library POSTs to the token endpoint with:

```
grant_type=client_credentials
client_id=<OAUTH_CLIENT_ID>
client_secret=<OAUTH_CLIENT_SECRET>
scope=openid
audience=<OAUTH_AUDIENCE>     # only if set
```

The token endpoint is either `OAUTH_TOKEN_URL` directly, or resolved via
OIDC discovery from `OAUTH_ISSUER`.

## Refresh behavior

Per RFC 6749 §4.4.3, the server **SHOULD NOT** return a refresh token for a
`client_credentials` response. The library handles this:

- If the response includes a refresh token, normal refresh-token rotation
  applies.
- If the response omits a refresh token (the common case), the library marks
  the token as "no refresh available" internally and re-runs
  `client_credentials` on the next expiry. No user credentials are involved,
  so re-authenticating is cheap.

## Constructing the client explicitly

If you'd rather not use env vars, pass the values as kwargs:

```python
client = GundiClient(
    base_url="https://api.gundiservice.org",
    oauth_issuer="https://auth.gundiservice.org/realms/your-realm",
    oauth_client_id="your-client-id",
    oauth_client_secret="your-client-secret",
    # oauth_audience="your-api-audience",
)
```

The kwargs win over env vars.

## See also

- [Password grant](password-grant.md) for user-facing flows
- [OIDC discovery](oidc-discovery.md) for the issuer-based token endpoint resolution
- [Refresh and errors](refresh-and-errors.md) for token-refresh internals
```

- [ ] **Step 2: Commit**

```bash
git add docs/authentication/client-credentials.md
git commit -m "docs: add Client credentials grant page"
```

---

## Task 11: Write `docs/authentication/password-grant.md`

**Files:**
- Create: `docs/authentication/password-grant.md`

- [ ] **Step 1: Write the page**

```markdown
# Password grant

The `password` grant (Resource Owner Password Credentials, ROPC; RFC 6749
§4.3) authenticates a user by sending their username and password directly
to the IdP.

!!! warning "ROPC is discouraged by OAuth 2.1"
    OAuth 2.1 (RFC 9700) discourages ROPC in favor of authorization-code
    flows with PKCE. `gundi-client-v2` supports it for legacy and CLI use
    cases where redirect-based flows aren't practical, and for public
    clients that don't have a secret.

## When to use it

- Your code runs in a context where you have the user's credentials
  (a CLI tool, a desktop utility, an internal admin script).
- Your OAuth client is **public** (no client secret).
- You need to act *as the user*, not as a system account.

## Environment variables

```env
GUNDI_API_BASE_URL=https://api.gundiservice.org
OAUTH_ISSUER=https://auth.gundiservice.org/realms/your-realm
OAUTH_CLIENT_ID=your-client-id
GUNDI_USERNAME=your-username
GUNDI_PASSWORD=your-password
# OAUTH_AUDIENCE=your-api-audience   # required by some IdPs (e.g. Auth0)
```

## Minimal example

```python
import asyncio
from gundi_client_v2 import GundiClient


async def main():
    async with GundiClient() as client:
        integrations = []
        async for integration in client.get_integrations():
            integrations.append(integration)
        print(f"User has access to {len(integrations)} integrations")


asyncio.run(main())
```

## What's on the wire

```
grant_type=password
client_id=<OAUTH_CLIENT_ID>
username=<GUNDI_USERNAME>
password=<GUNDI_PASSWORD>
scope=openid
audience=<OAUTH_AUDIENCE>     # only if set
```

No `client_secret` — public clients don't have one.

## Refresh behavior

A successful password-grant response typically includes a `refresh_token`.
The library caches it and uses it on the next expiry (RFC 6749 §6) to avoid
re-sending the user's credentials.

If the server rotates the refresh token on each refresh (default in
Keycloak), the new one replaces the cached one. If the server omits a new
refresh token in the refresh response (also allowed by §6), the library
reuses the existing cached refresh token until it too expires.

When the refresh token itself expires, the library falls back to a fresh
password grant — provided `GUNDI_USERNAME` and `GUNDI_PASSWORD` are still
in the env. If they've been unset, you'll see an `AuthenticationError`.

## Constructing the client explicitly

```python
client = GundiClient(
    base_url="https://api.gundiservice.org",
    oauth_issuer="https://auth.gundiservice.org/realms/your-realm",
    oauth_client_id="your-client-id",
    username="your-username",
    password="your-password",
)
```

## See also

- [Client credentials](client-credentials.md) for confidential M2M clients
- [OIDC discovery](oidc-discovery.md) for issuer-based token endpoint resolution
- [Refresh and errors](refresh-and-errors.md) for refresh-rotation details
```

- [ ] **Step 2: Commit**

```bash
git add docs/authentication/password-grant.md
git commit -m "docs: add Password grant page"
```

---

## Task 12: Write `docs/authentication/oidc-discovery.md`

**Files:**
- Create: `docs/authentication/oidc-discovery.md`

- [ ] **Step 1: Write the page**

```markdown
# OIDC discovery

OIDC Discovery 1.0 specifies that any OIDC-compliant IdP MUST expose a
metadata document at `{issuer}/.well-known/openid-configuration`. That
document includes the `token_endpoint`, `authorization_endpoint`, supported
scopes, and other configuration.

`gundi-client-v2` uses this to **avoid hard-coding** the token endpoint URL.
Set `OAUTH_ISSUER` to the IdP's issuer base URL, and the library fetches and
caches the resolved token endpoint at runtime.

## When to use it

- You don't want to look up and hard-code the exact token endpoint URL.
- You're rolling the same code out against multiple IdPs (Keycloak,
  Auth0, Okta, Azure AD).
- You want to be resilient to the IdP team changing the token endpoint
  path (rare, but possible).

## Environment variable

```env
OAUTH_ISSUER=https://auth.gundiservice.org/realms/your-realm
```

Combine with the credentials for your chosen grant
([client_credentials](client-credentials.md) or
[password](password-grant.md)).

## What happens at runtime

1. The first authentication attempt calls
   `auth.discover_token_endpoint(session, issuer)`.
2. The function GETs `{issuer.rstrip('/')}/.well-known/openid-configuration`.
3. It validates that the document's `issuer` claim matches the URL used to
   fetch it (OIDC Discovery 1.0 §4.3 — protects against
   misconfiguration and man-in-the-middle).
4. The resolved `token_endpoint` is cached in a module-level dict keyed by
   the normalized issuer.
5. Subsequent authentication attempts reuse the cached value.

The cache lives for the process lifetime. Long-running services that need
to pick up an IdP configuration change without restarting can call:

```python
from gundi_client_v2.auth import clear_discovery_cache

clear_discovery_cache()
```

## Performance note

OIDC discovery adds **one** extra HTTP request to the very first
authentication. Subsequent requests in the same process do no additional
network I/O for discovery.

## Skipping discovery

If your IdP doesn't expose a discovery document, or you want to skip the
extra request, set `OAUTH_TOKEN_URL` directly instead. When both are set,
`OAUTH_TOKEN_URL` wins:

```env
OAUTH_TOKEN_URL=https://auth.example.com/realms/myrealm/protocol/openid-connect/token
```

## Errors

| Error | Meaning |
|---|---|
| `OIDC discovery failed for ...` | Network error or non-2xx response fetching the discovery document. Check connectivity and that the issuer URL is correct. |
| `OIDC discovery document at ... is not valid JSON` | The discovery endpoint returned something that isn't JSON. Check that the URL is correct and not returning an HTML error page. |
| `OIDC discovery document at ... is not a JSON object` | The endpoint returned JSON, but not an object. Almost certainly an IdP bug. |
| `OIDC discovery document at ... returned issuer ... which does not match the expected issuer ...` | The `issuer` claim in the discovery doc doesn't match the URL used to fetch it. Common cause: trailing slash mismatch (the library normalizes both via `rstrip('/')`, so this shouldn't trip you up), or IdP misconfiguration. |
| `OIDC discovery document at ... is missing 'token_endpoint'` | The IdP exposed a discovery document but didn't include the required `token_endpoint` field. Almost certainly an IdP bug. |

## See also

- [Refresh and errors](refresh-and-errors.md) for general auth-error handling
- The full example: [`examples/list_connections_discovery.py`](https://github.com/PADAS/gundi-client/blob/v2/examples/list_connections_discovery.py)
```

- [ ] **Step 2: Commit**

```bash
git add docs/authentication/oidc-discovery.md
git commit -m "docs: add OIDC discovery page"
```

---

## Task 13: Write `docs/authentication/refresh-and-errors.md`

**Files:**
- Create: `docs/authentication/refresh-and-errors.md`

- [ ] **Step 1: Write the page**

```markdown
# Refresh and errors

How the library reuses tokens, when it re-authenticates, and the errors
you'll see when something goes wrong.

## Token lifecycle inside `GundiClient`

The client caches the most recent `OAuthToken` in memory, along with two
computed timestamps:

- `expires_at` — when the access token will become invalid
- `refresh_expires_at` — when the refresh token will become invalid

Both have a small safety buffer (15 seconds) subtracted so the client treats
a token as expired slightly *before* the server does.

On every authenticated request, the client checks:

1. **Is the access token still valid?** → Use it.
2. **Is the refresh token still valid?** → Refresh and use the new access
   token (RFC 6749 §6).
3. **Otherwise** → Re-authenticate via the configured grant.

## Refresh token rotation

RFC 6749 §6 makes returning a new refresh token in the refresh response
**optional**. Two scenarios:

**Rotating IdP** (Keycloak default, most modern IdPs): every refresh
response includes a new `refresh_token` that replaces the previous one. The
client treats this as the canonical behavior and updates its cache.

**Non-rotating IdP**: the refresh response includes only a new access token,
no new refresh token. The client recognizes this case, keeps the existing
cached refresh token, and continues using it until the IdP rejects it.

You don't have to do anything to support either case — the library detects
which one your IdP is using.

## `client_credentials` re-authentication

`client_credentials` responses don't usually include a refresh token (per
RFC 6749 §4.4.3). The client treats these tokens as "no refresh available":
when they expire, it runs the `client_credentials` grant again. Because no
user credentials are involved, this is cheap.

## Common errors

### `Token request failed: HTTP 401 (invalid_client)`

The client ID or secret is wrong, or the client doesn't exist in the realm.

**Fix:** Verify `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET`. For Keycloak,
also confirm the client is in the correct realm under `OAUTH_ISSUER`.

### `Token request failed: HTTP 401 (invalid_grant)`

The credentials don't match a user (password grant), or the refresh token
has been revoked or expired (refresh grant).

**Fix:** For password grant, verify `GUNDI_USERNAME` and `GUNDI_PASSWORD`.
For refresh grant, the client should fall back to a fresh password/client_
credentials grant automatically; if it doesn't, check that the fallback
credentials are still in the env.

### `Token request failed: HTTP 401 (unauthorized_client)`

The client isn't permitted to use this grant type at the IdP. Common in
Keycloak when "Direct Access Grants Enabled" (password grant) or "Service
Accounts Enabled" (client_credentials) hasn't been toggled on for the
client.

**Fix:** Ask your IdP administrator to enable the appropriate grant for the
client.

### `Token request failed: HTTP 400 (invalid_scope)`

The requested scope isn't allowed for this client.

**Fix:** Pass a `scope=...` kwarg to the grant function, or unset
`OAUTH_SCOPE` if you set it explicitly. The library's default scope is
`openid`.

### `AuthenticationError: OIDC discovery failed for ...`

See [OIDC discovery → Errors](oidc-discovery.md#errors).

## Handling auth errors in your code

`AuthenticationError` is a subclass of `gundi_client_v2.errors.GundiClientError`.
Catch it around your client calls if you want to handle expired credentials
gracefully:

```python
from gundi_client_v2 import GundiClient
from gundi_client_v2.errors import AuthenticationError


async def main():
    try:
        async with GundiClient() as client:
            connections = await client.get_connections()
    except AuthenticationError as e:
        print(f"Auth failed: {e}")
        # ... fetch new credentials, prompt user, exit, etc.
```

## See also

- [Overview](overview.md) for the grant-selection logic
- [Troubleshooting](../troubleshooting.md) for non-auth errors
```

- [ ] **Step 2: Commit**

```bash
git add docs/authentication/refresh-and-errors.md
git commit -m "docs: add Refresh and errors page"
```

---

## Task 14: Write `docs/reading-data/connections.md`

**Files:**
- Create: `docs/reading-data/connections.md`

- [ ] **Step 1: Write the page**

```markdown
# Reading Connections

A **Connection** groups one or more provider Integrations with their
destination Integrations and the Routes between them. See
[Gundi data model](../concepts/data-model.md) for the conceptual overview.

The client exposes two methods for reading Connections:

| Method | Returns | Notes |
|---|---|---|
| `get_connections(params=None)` | `List[Connection]` | Lists all Connections accessible to the authenticated principal |
| `get_connection_details(integration_id)` | `Connection` | Fetches a single Connection by its provider Integration's ID |

## List all connections

```python
import asyncio
from gundi_client_v2 import GundiClient


async def main():
    async with GundiClient() as client:
        connections = await client.get_connections()
        for c in connections:
            print(c.id, c.name, c.status)


asyncio.run(main())
```

## Filtering

`get_connections()` accepts a `params` dict that's passed through to the
API as query-string parameters. Common filters:

```python
# Only healthy connections
healthy = await client.get_connections(params={"status": "healthy"})

# Only connections owned by a specific organization
owned = await client.get_connections(params={"owner": "<organization-id>"})

# Search by name (substring match)
named = await client.get_connections(params={"search": "TrapTagger"})
```

The exact set of available filters depends on the Gundi API version your
deployment exposes. Consult your deployment's API docs for the complete
list; pass anything documented there as a key in `params`.

## Pagination

`get_connections()` handles pagination transparently — it walks the
`next` cursor from the API's paginated response and returns the
**accumulated list**.

For large result sets where you want streaming behavior, fall back to
manual pagination by passing the cursor parameters explicitly through
`params`.

## Fetch one connection

```python
connection = await client.get_connection_details(
    integration_id="ddd0946d-15b0-4308-b93d-e0470b6d33b6"
)
print(connection.dict())
```

The `integration_id` is the ID of the **provider** Integration. If you don't
have it, list connections and pick the one you want by name or status:

```python
connections = await client.get_connections(params={"status": "healthy"})
target = next(c for c in connections if c.name == "TrapTagger PADAS")
print(target.id)
```

## The `Connection` model

Defined in `gundi_core.schemas.v2.Connection`. Key fields:

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Connection's unique identifier |
| `name` | `str` | Human-readable name |
| `status` | `str` | `healthy`, `unhealthy`, `disabled` |
| `provider` | `Integration` | The provider Integration |
| `destinations` | `List[Integration]` | One or more destination Integrations |
| `routing_rules` | `List[UUID]` | Route IDs that apply to this Connection |
| `default_route` | `Optional[UUID]` | The default Route ID, if any |
| `owner` | `Organization` | The owning Organization |

For the canonical field list, see the
[`gundi-core` source](https://github.com/PADAS/gundi-core/blob/main/gundi_core/schemas/v2/gundi.py).

## Output as JSON

`Connection` is a Pydantic v1 model — call `.dict()` to get a plain dict, or
serialize directly with `json.dumps`:

```python
import json

connections = await client.get_connections()
print(json.dumps([c.dict() for c in connections], default=str, indent=2))
```

`default=str` handles `UUID`, `datetime`, and other non-JSON-native types.

## See also

- [Reading Integrations](integrations.md) for individual provider/destination details
- [Connection example script](https://github.com/PADAS/gundi-client/blob/v2/examples/list_connections_client_credentials.py) in the repo
```

- [ ] **Step 2: Commit**

```bash
git add docs/reading-data/connections.md
git commit -m "docs: add Reading Connections page"
```

---

## Task 15: Write `docs/reading-data/integrations.md`

**Files:**
- Create: `docs/reading-data/integrations.md`

- [ ] **Step 1: Write the page**

```markdown
# Reading Integrations

An **Integration** is a single registered third-party system — either a
provider (e.g. a TrapTagger camera trap) or a destination (e.g. an
EarthRanger site). See [Gundi data model](../concepts/data-model.md) for
context.

The client exposes three methods:

| Method | Returns | Notes |
|---|---|---|
| `get_integrations(params=None)` | `AsyncGenerator[Integration]` | Streams all Integrations matching the filters |
| `get_integration_details(integration_id)` | `Integration` | Fetches one Integration by ID |
| `get_integration_api_key(integration_id)` | `dict` with `api_key` | Used to bootstrap a `GundiDataSenderClient` |

## List integrations (async generator)

Unlike `get_connections`, `get_integrations` is an **async generator** —
iterate it with `async for`:

```python
import asyncio
from gundi_client_v2 import GundiClient


async def main():
    async with GundiClient() as client:
        async for integration in client.get_integrations():
            print(integration.id, integration.name, integration.type)


asyncio.run(main())
```

Why a generator? The Integrations endpoint paginates aggressively for large
deployments. Streaming lets your code start processing as the first page
arrives rather than waiting for the full list.

If you need a list anyway, materialize it:

```python
integrations = [i async for i in client.get_integrations()]
```

## Filtering

```python
# Only provider-type Integrations
async for i in client.get_integrations(params={"action_type": "pull_observations"}):
    print(i.name)

# Search by name substring
async for i in client.get_integrations(params={"search": "lotek"}):
    print(i.name, i.id)
```

Consult your Gundi API's documentation for the full set of filter keys.

## Fetch one integration

```python
integration = await client.get_integration_details(
    integration_id="338225f3-91f9-4fe1-b013-353a229ce504"
)
print(integration.dict())
```

## Get an Integration's API key

Some workflows need the per-Integration API key to send observations or
events directly through Gundi's data ingestion API. Fetch it with:

```python
key_response = await client.get_integration_api_key(
    integration_id="338225f3-91f9-4fe1-b013-353a229ce504"
)
api_key = key_response["api_key"]
```

Then pass it to `GundiDataSenderClient`:

```python
from gundi_client_v2 import GundiDataSenderClient

async with GundiDataSenderClient(integration_api_key=api_key) as sender:
    await sender.post_observations(data=[{...}])
```

(Sending observations is covered in Phase 2 of these docs.)

## The `Integration` model

Defined in `gundi_core.schemas.v2.Integration`. Key fields:

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Integration's unique identifier |
| `name` | `str` | Human-readable name |
| `type` | `IntegrationType` | Slug + display name of the system type |
| `base_url` | `str` | URL of the third-party system, if applicable |
| `enabled` | `bool` | Whether Gundi is actively pulling/pushing |
| `owner` | `Organization` | The owning Organization |
| `configurations` | `List[IntegrationActionConfiguration]` | Per-action configuration |
| `webhook_configuration` | `Optional[IntegrationWebhookConfiguration]` | Webhook-specific config |

For the canonical field list, see the
[`gundi-core` source](https://github.com/PADAS/gundi-core/blob/main/gundi_core/schemas/v2/gundi.py).

## Output as JSON

```python
import json

integrations = [i async for i in client.get_integrations()]
print(json.dumps([i.dict() for i in integrations], default=str, indent=2))
```

## See also

- [Reading Connections](connections.md) — group Integrations by provider/destination
- [Send observations example](https://github.com/PADAS/gundi-client/blob/v2/examples/send_observations.py)
```

- [ ] **Step 2: Commit**

```bash
git add docs/reading-data/integrations.md
git commit -m "docs: add Reading Integrations page"
```

---

## Task 16: Write `docs/migration.md` (snippet from MIGRATION.md)

**Files:**
- Create: `docs/migration.md`

- [ ] **Step 1: Create the migration page using a pymdownx snippet**

```markdown
---
title: Migration (2.x → 3.0)
---

--8<-- "MIGRATION.md"
```

The `--8<--` syntax pulls in the root `MIGRATION.md` verbatim. The
`base_path` is configured in `mkdocs.yml` (`pymdownx.snippets.base_path:
["."]`).

- [ ] **Step 2: Verify the snippet renders**

```bash
mkdocs build --strict 2>&1 | grep -i migration | head -5
```

Expected: no errors mentioning migration.

- [ ] **Step 3: Commit**

```bash
git add docs/migration.md
git commit -m "docs: add Migration page sourced from MIGRATION.md"
```

---

## Task 17: Write `docs/troubleshooting.md`

**Files:**
- Create: `docs/troubleshooting.md`

- [ ] **Step 1: Write the page**

```markdown
# Troubleshooting

Common errors when using `gundi-client-v2`, with their causes and fixes.

## Authentication errors

See [Authentication → Refresh and errors](authentication/refresh-and-errors.md)
for the full catalog with explanations.

## `httpx.ConnectError: [Errno -2] Name or service not known`

The hostname in `GUNDI_API_BASE_URL` or `OAUTH_ISSUER` doesn't resolve.

**Fix:** Verify the URLs are correct and reachable from the host running
your code. Common gotchas:

- Typos in the host (`gundiservice.org` vs `gundiserice.org`)
- Missing `https://` scheme
- Internal hostnames that don't resolve outside a VPN

## `httpx.ConnectTimeout` or `httpx.ReadTimeout`

The server isn't responding within the configured timeout.

**Fix:** Increase timeouts at construction time:

```python
import httpx
from gundi_client_v2 import GundiClient

client = GundiClient(
    transport=httpx.AsyncHTTPTransport(),
    timeout=httpx.Timeout(60.0),  # 60 seconds for all phases
)
```

## `TypeError: Client.__init__() got an unexpected keyword argument 'app'`

You're on `httpx>=0.28` but `starlette<0.37`. This usually surfaces in
FastAPI test code (`TestClient(app)`).

**Fix:** See [Migration → Troubleshooting](migration.md#troubleshooting).
Short version: bump `fastapi` to `>=0.110.3` (which allows
`starlette>=0.37`).

## `ValidationError` from Pydantic when parsing a response

The API returned a payload that doesn't match the expected `gundi-core`
schema. This typically happens during version skew (your client and the
server are out of sync) or for newly-introduced fields.

**Fix:**
- Confirm the deployed Gundi version matches your client major version.
- If the field is benign, you may need to upgrade `gundi-core` to a release
  that knows about it.
- If you suspect a server bug, capture the raw response by intercepting
  the HTTPX transport and report it to your Gundi administrator.

## `GundiAPIError: HTTP 403`

The authenticated principal doesn't have permission to access the
requested resource.

**Fix:** Check that your client/user has the necessary roles in the IdP
realm. For per-Integration resources, your principal must own or be
granted access to that Integration's Organization.

## `GundiAPIError: HTTP 404`

The resource doesn't exist or you don't have permission to see it (some
APIs return 404 instead of 403 to avoid leaking resource existence).

**Fix:** Verify the ID is correct. If you have an `integration_id` from
elsewhere, confirm it actually exists with
`client.get_integration_details(integration_id)`.

## Stuck?

- Check the [Authentication overview](authentication/overview.md) for
  grant-selection issues.
- Check the [Migration guide](migration.md) if you recently upgraded.
- Open an issue at
  [github.com/PADAS/gundi-client/issues](https://github.com/PADAS/gundi-client/issues).
```

- [ ] **Step 2: Commit**

```bash
git add docs/troubleshooting.md
git commit -m "docs: add Troubleshooting page"
```

---

## Task 18: Write `docs/changelog.md` (link to GitHub releases)

**Files:**
- Create: `docs/changelog.md`

- [ ] **Step 1: Write the page**

```markdown
# Changelog

The canonical changelog for `gundi-client-v2` is the
**[GitHub Releases page](https://github.com/PADAS/gundi-client/releases)**.

Each release tag (`vX.Y.Z`) has a description summarizing what changed,
linked PRs, and the wheel/sdist artifacts attached.

For the latest version notes, follow that link.

## Major release migration guides

- **2.x → 3.0** — [Migration guide](migration.md)
```

- [ ] **Step 2: Commit**

```bash
git add docs/changelog.md
git commit -m "docs: add Changelog page linking to GitHub Releases"
```

---

## Task 19: Verify the full build passes strict mode

**Files:** none (verification step)

- [ ] **Step 1: Run a strict build**

```bash
mkdocs build --strict
```

Expected: build succeeds with no warnings or errors. If you see a warning
about a missing nav target or a broken internal link, fix it before
proceeding.

- [ ] **Step 2: Preview the site locally**

```bash
mkdocs serve
```

Expected: server starts on `http://127.0.0.1:8000`. Open it, click through
every nav item, confirm every page renders, every link works.

Stop the server with Ctrl-C when done.

- [ ] **Step 3: If anything's broken, fix it and commit the fix**

```bash
git add <fixed-files>
git commit -m "docs: fix <description-of-fix>"
```

---

## Task 20: Push branch and open PR

**Files:** none (workflow step)

- [ ] **Step 1: Push the branch**

```bash
git push -u origin cd/v2-docs-site
```

- [ ] **Step 2: Open the PR with `gh`**

Use a quoted heredoc so the markdown backticks and brackets pass through verbatim:

```bash
gh pr create --base v2 --head cd/v2-docs-site \
  --title "docs: stand up MkDocs site (Phase 1)" \
  --body "$(cat <<'BODY'
## Summary

Stands up a MkDocs Material documentation site for `gundi-client-v2`, deployed to GitHub Pages on push to `v2`. Phase 1 of the design in [the spec](https://github.com/PADAS/gundi-client/blob/cd/v2-docs-site/docs/superpowers/specs/2026-06-01-gundi-client-v2-docs-site-design.md).

## What's included

- Site infrastructure: `mkdocs.yml`, `.github/workflows/docs.yml`, `[project.optional-dependencies] docs` group
- Pages: Home, Installation, Authentication setup, First request, Gundi data model, four Authentication pages, Reading Connections, Reading Integrations, Migration, Troubleshooting, Changelog (link to releases)
- Auto-generated API reference (mkdocstrings) is deferred to Phase 2 along with sending data, routes, recipes, and the full API ref.

## Verification

- `mkdocs build --strict` passes (no broken links, no missing nav targets).
- `mkdocs serve` confirms every page renders.
- The docs workflow will deploy to gh-pages on merge.

## Plan

[`docs/superpowers/plans/2026-06-01-gundi-client-v2-docs-site-phase-1.md`](https://github.com/PADAS/gundi-client/blob/cd/v2-docs-site/docs/superpowers/plans/2026-06-01-gundi-client-v2-docs-site-phase-1.md)
BODY
)"
```

- [ ] **Step 3: Verify the PR was created**

```bash
gh pr view --json url,title,state | head -10
```

Expected: a JSON blob with the new PR's URL.

---

## Self-review checklist

After all tasks above are complete, run through this final check before merging:

- [ ] **Spec coverage:** Every page promised in the spec's "Phase 1" content list is present.
- [ ] **No placeholders:** No "TBD", "TODO", "coming soon" in any page (admonition placeholders explicitly removed).
- [ ] **Internal links:** Every relative link (`../foo/bar.md`) resolves. `mkdocs build --strict` catches these.
- [ ] **Code examples:** Every Python example imports the names it uses. Every shell command has the expected output described.
- [ ] **Audience:** Every page reads naturally to a developer who has just discovered the library — no PADAS-internal jargon, no assumptions about Keycloak or OIDC beyond what the page itself explains.
- [ ] **Migration page:** Renders the root `MIGRATION.md` cleanly. No double headings.
- [ ] **Workflow:** `.github/workflows/docs.yml` triggers on push to `v2`. On merge of this PR, that triggers — confirm the run completes and the site is reachable.

## Deferred to Phase 2

- Pages: Observations vs Events vs Messages, Tracing and lifecycle, Reading Routes, Reading Traces, Sending Observations/Events/Messages, all of Recipes, Troubleshooting deepening, Changelog auto-pull
- Auto-generated API reference via mkdocstrings (requires docstring audit of `client.py`)
- Anything that requires running an example against a live Gundi deployment for verification screenshots
