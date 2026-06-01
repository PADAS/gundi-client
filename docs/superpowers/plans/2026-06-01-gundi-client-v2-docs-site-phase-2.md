# gundi-client-v2 docs site — Phase 2 implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the gundi-client-v2 documentation site — add Concepts, Sending data, Reading Routes/Traces, Recipes, and an auto-generated API reference, backed by a docstring audit of the public surface.

**Architecture:** Continue building on the MkDocs Material site from Phase 1. Add the `mkdocstrings-python` plugin so the API reference renders from in-source docstrings. Audit and improve docstrings on every public method/function/class so the API ref is useful. All changes ship in a single PR.

**Tech Stack:** MkDocs Material 9.5+, mkdocstrings-python 1.x, Google-style docstrings, GitHub Actions.

**Spec:** [`docs/superpowers/specs/2026-06-01-gundi-client-v2-docs-site-phase-2.md`](../specs/2026-06-01-gundi-client-v2-docs-site-phase-2.md)

**Branch:** `cd/v2-docs-site-phase2` (cut from `cd/v2-docs-site` — Phase 1's branch).

---

## File map

### Source changes (docstring audit, non-behavioral)

| Path | Change |
|---|---|
| `gundi_client_v2/client.py` | Add/expand Google-style docstrings on every public method of `GundiClient` and `GundiDataSenderClient`. No signature changes. |
| `gundi_client_v2/auth.py` | Verify and tighten docstrings on standalone public functions. |
| `gundi_client_v2/errors.py` | One-line class docstrings minimum; document `GundiAPIError.__init__` args. |

### Infrastructure changes

| Path | Change |
|---|---|
| `pyproject.toml` | Add `mkdocstrings[python]>=0.24` to `[project.optional-dependencies] docs`. |
| `mkdocs.yml` | Add `mkdocstrings` to the `plugins` list with Google docstring style; extend `nav` with new sections. |

### New content pages

| Path | Section |
|---|---|
| `docs/concepts/payload-types.md` | Concepts |
| `docs/concepts/tracing-lifecycle.md` | Concepts |
| `docs/reading-data/routes.md` | Reading data |
| `docs/reading-data/traces.md` | Reading data |
| `docs/sending-data/observations.md` | Sending data |
| `docs/sending-data/events.md` | Sending data |
| `docs/sending-data/messages-attachments.md` | Sending data |
| `docs/recipes/pagination.md` | Recipes |
| `docs/recipes/filtering.md` | Recipes |
| `docs/recipes/custom-httpx.md` | Recipes |
| `docs/recipes/error-handling.md` | Recipes |
| `docs/api-reference/index.md` | API reference |
| `docs/api-reference/gundi-client.md` | API reference |
| `docs/api-reference/data-sender-client.md` | API reference |
| `docs/api-reference/auth.md` | API reference |
| `docs/api-reference/errors.md` | API reference |

### Existing-page updates

| Path | Change |
|---|---|
| `docs/index.md` | Add new sections to the "How this site is organized" table. |
| `docs/troubleshooting.md` | Cross-link to `recipes/error-handling.md`. |

---

## Verified facts (use these when writing pages)

These are confirmed against `gundi_client_v2/` source and `gundi-core` schemas as of branch HEAD:

### `GundiDataSenderClient` (client.py:25-122)

- Constructor: `GundiDataSenderClient(integration_api_key=None, sensors_api_base_url=None)`. Reads `SENSORS_API_BASE_URL` env var as fallback.
- Auth: uses the `apikey` HTTP header. **No OAuth flow.** The API key is fetched separately via `GundiClient.get_integration_api_key(integration_id)`.
- All `post_*` methods take `data: List[dict]` and return `dict` (the raw JSON response).
- `update_event(event_id, data)` takes `data: dict` (single, not a list) and uses HTTP PATCH.
- `post_event_attachments(event_id, attachments)` takes `attachments: List[tuple]` where each tuple is `(filename, file_binary)`. Sent as multipart form field `file`.
- HTTPX timeout is hard-coded at 120 seconds inside `_post_data` and `_update_data`. Not configurable via the constructor.
- Errors: calls `errors.raise_for_status(response)` which raises `GundiAPIError` on 4xx/5xx.

### `gundi_core.schemas.v2.GundiTrace` (Trace model)

Fields:
- `object_id: Union[UUID, str]` — the source observation/event ID
- `object_type: str` — payload type discriminator
- `related_to: Optional[Union[UUID, str]]` — links to a parent object (e.g. an event the trace's observation belongs to)
- `data_provider: Optional[Union[UUID, str]]` — provider Integration ID
- `destination: Optional[Union[UUID, str]]` — destination Integration ID
- `delivered_at: datetime` — when the payload reached the destination
- `external_id: Optional[Union[UUID, str]]` — the ID assigned by the destination
- `created_at: datetime` — when Gundi recorded the trace
- `updated_at: datetime` — last update to the trace
- `last_update_delivered_at: datetime` — when the most recent update was delivered
- `is_duplicate: bool` — whether Gundi suppressed this as a duplicate
- `has_error: bool` — whether delivery errored

### `gundi_core.schemas.v2.Route`

Fields:
- `id: Union[UUID, str]`
- `name: str`
- `owner: Optional[Union[UUID, str]]` — organization ID
- `data_providers: List[ConnectionIntegration]` — provider Integrations
- `destinations: List[ConnectionIntegration]` — destination Integrations
- `configuration: RouteConfiguration` — transformation rules (often a JQ filter)
- `additional: Dict[str, Any]`

### `gundi_client_v2.errors`

Three exception classes:
- `GundiClientError(Exception)` — base
- `AuthenticationError(GundiClientError)` — OAuth token retrieval / auth failures
- `GundiAPIError(GundiClientError)` — 4xx/5xx HTTP responses. `__init__(status_code: int, detail: str = "")`. Exposes `.status_code` and `.detail`.

Plus `raise_for_status(response)` helper.

### `GundiClient` public methods on the read surface (client.py:387-475)

- `get_connections(params=None) → List[Connection]` — first page only
- `get_connection_details(integration_id) → Connection`
- `get_routes(params=None) → List[Route]` — first page only
- `get_routes_for_connection(connection_id) → List[Route]` — convenience for `get_routes(params={"provider": ...})`
- `get_route_details(route_id) → Route`
- `create_route(data: dict) → Route`
- `update_route(route_id, data: dict) → Route` (HTTP PATCH)
- `delete_route(route_id) → None` (HTTP DELETE, returns None on 204)
- `get_integrations(params=None) → AsyncGenerator[Integration, None]` — walks the `next` cursor transparently
- `get_integration_details(integration_id) → Integration`
- `get_integration_api_key(integration_id) → str` — returns the API key string directly
- `get_traces(params: dict) → List[GundiTrace]` — first page only
- `register_integration_type(data: dict)` — admin/internal use; document but don't promote in tutorials

---

## Task 1: Docstring audit — `gundi_client_v2/client.py`

**Files:**
- Modify: `gundi_client_v2/client.py`

This is the largest task in the plan. Approach: read every public method on `GundiClient` and `GundiDataSenderClient`, add/expand the docstring using the Google template below. Internal helpers (`_get`, `_post`, `_resolve_token_url`, etc.) are out of scope.

### Google docstring template

Use this shape for every method:

```python
async def get_connections(self, params: dict = None) -> List[Connection]:
    """List Connections accessible to the authenticated principal.

    Returns the first page of results only (the Gundi API default
    page size is 20). For paginated walking, see
    :doc:`/recipes/pagination`.

    Args:
        params: Optional dict of query parameters passed through to
            the API. Common keys: ``status`` (``healthy``,
            ``unhealthy``, ``disabled``), ``owner`` (organization ID),
            ``search`` (substring match).

    Returns:
        List of :class:`gundi_core.schemas.v2.Connection` objects.

    Raises:
        AuthenticationError: If the OAuth token request fails.
        GundiAPIError: If the API returns a 4xx/5xx response.
    """
```

Rules:
- One-line summary at the top (imperative or third-person, your choice — be consistent within the file).
- Blank line after the summary, then any extended description.
- `Args:` section with each parameter on its own indented line.
- `Returns:` describing the value (omit if `None`).
- `Raises:` listing exceptions the method can raise. Include `AuthenticationError` for any method that calls `get_auth_header()`. Include `GundiAPIError` for any method that calls `_raise_for_status`.
- Don't restate types in the Args section — mkdocstrings picks them up from the signature.
- Don't use rST directives like `:class:`; use plain text or backticks. mkdocstrings handles cross-refs differently than Sphinx.

### Methods to document

**`GundiDataSenderClient`:**

- `__init__(self, integration_api_key, **kwargs)` — note that `integration_api_key` is fetched via `GundiClient.get_integration_api_key`.
- `post_observations(self, data)` — note that `data` is a list of observation dicts; document the response shape briefly (the raw JSON from the API).
- `post_events(self, data)` — same.
- `post_messages(self, data)` — same.
- `update_event(self, event_id, data)` — PATCH semantics.
- `post_event_attachments(self, event_id, attachments)` — explain the `(filename, file_binary)` tuple format.

**`GundiClient`:**

- `__init__(self, **kwargs)` — list every named kwarg the constructor reads (base_url, oauth_token_url, oauth_issuer, oauth_client_id, oauth_client_secret, oauth_audience, oauth_scope, username, password, connect_timeout, data_timeout, max_http_retries, use_ssl, plus the keycloak_ aliases).
- `close(self)` — closes the HTTPX session.
- `__aenter__` / `__aexit__` — brief notes.
- `get_access_token(self, force_refresh_token=False)` — returns the cached `OAuthToken`; refreshes if expired.
- `get_auth_header(self, force_refresh_token=False)` — returns the `Authorization: Bearer ...` header dict.
- `get_connections(self, params=None)` — full Google docstring per template above.
- `get_connection_details(self, integration_id)`
- `get_routes(self, params=None)`
- `get_routes_for_connection(self, connection_id)`
- `get_route_details(self, route_id)`
- `create_route(self, data)`
- `update_route(self, route_id, data)`
- `delete_route(self, route_id)`
- `get_integrations(self, params=None)` — note the AsyncGenerator return; recommend `async for`.
- `get_integration_details(self, integration_id)`
- `get_integration_api_key(self, integration_id)` — returns the API key **string**, not a dict.
- `get_traces(self, params)` — first page only.
- `register_integration_type(self, data)` — administrative use.

- [ ] **Step 1: Read client.py** to refresh on each method's current state.

- [ ] **Step 2: Apply docstring improvements** to every method listed above. Work through them top-to-bottom in the file. Keep edits surgical — only the docstring blocks change.

- [ ] **Step 3: Verify nothing was broken**

```bash
pytest -x --tb=short
```

Expected: full test suite passes with the same number of tests as before (currently 73). Any failure means a non-docstring change leaked in.

- [ ] **Step 4: Commit**

```bash
git add gundi_client_v2/client.py
git commit -m "docs(api): add Google-style docstrings to GundiClient and GundiDataSenderClient

Covers every public method; no signature changes. Establishes Args/Returns/
Raises sections so mkdocstrings-python can render a useful API reference
section in the docs site."
```

---

## Task 2: Docstring audit — `gundi_client_v2/auth.py` and `errors.py`

**Files:**
- Modify: `gundi_client_v2/auth.py`
- Modify: `gundi_client_v2/errors.py`

`auth.py` already has good docstrings on most functions. This pass:
1. Verify each existing docstring uses the Google template structure (Args / Returns / Raises sections).
2. Add docstrings where missing.
3. Make sure the language is consistent with `client.py`.

`errors.py` needs:
- One-line class docstring on each exception (already mostly there).
- A class-level docstring on `GundiAPIError` that documents `status_code` and `detail` as instance attributes (since they're set in `__init__`, not declared as type hints).

### Functions to verify in `auth.py`

- `_extract_oauth_error(response)` — internal but used; brief one-liner.
- `_post_token(session, oauth_token_url, payload)` — internal but used; brief.
- `_token_request(session, oauth_token_url, payload)` — internal.
- `get_access_token_password_grant(...)` — needs Args/Returns/Raises.
- `refresh_access_token(...)` — already has good content; verify shape.
- `get_access_token_client_credentials(...)` — already has good content; verify shape.
- `clear_discovery_cache()` — already good.
- `discover_token_endpoint(session, issuer)` — already good; verify Returns and Raises are clear.

### Classes to verify in `errors.py`

- `GundiClientError` — class docstring present, fine.
- `AuthenticationError` — present.
- `GundiAPIError` — present; add an `Attributes:` block documenting `status_code` and `detail` on the instance.
- `raise_for_status(response)` function — already good.

- [ ] **Step 1: Apply docstring updates** to both files.

- [ ] **Step 2: Run tests**

```bash
pytest -x --tb=short
```

Expected: 73 tests pass.

- [ ] **Step 3: Commit**

```bash
git add gundi_client_v2/auth.py gundi_client_v2/errors.py
git commit -m "docs(api): tighten docstrings on auth functions and error classes

Normalize to Google-style across the public surface; add Attributes block
on GundiAPIError documenting status_code/detail."
```

---

## Task 3: Wire up mkdocstrings-python

**Files:**
- Modify: `pyproject.toml`
- Modify: `mkdocs.yml`

### Step 1: Add `mkdocstrings[python]` to the docs dep group

- [ ] Edit `pyproject.toml`'s `[project.optional-dependencies]` block from:

```toml
[project.optional-dependencies]
docs = [
    "mkdocs-material>=9.5",
    "mkdocs-exclude>=1.0",
]
```

to:

```toml
[project.optional-dependencies]
docs = [
    "mkdocs-material>=9.5",
    "mkdocs-exclude>=1.0",
    "mkdocstrings[python]>=0.24",
]
```

- [ ] Reinstall the docs extras:

```bash
uv pip install -e ".[docs]"
```

Expected: `mkdocstrings` and `mkdocstrings-python` install.

### Step 2: Add the mkdocstrings plugin config in `mkdocs.yml`

- [ ] In `mkdocs.yml`, find the `plugins:` block. It currently has:

```yaml
plugins:
  - search
  - exclude:
      glob:
        - "superpowers/**"
```

Add `mkdocstrings` configured for Google-style Python docstrings:

```yaml
plugins:
  - search
  - exclude:
      glob:
        - "superpowers/**"
  - mkdocstrings:
      handlers:
        python:
          paths: [.]
          options:
            docstring_style: google
            show_source: false
            show_root_heading: true
            show_root_toc_entry: false
            members_order: source
            heading_level: 2
            separate_signature: true
            line_length: 80
            show_signature_annotations: true
```

### Step 3: Add the API reference section to `nav`

- [ ] In the `nav:` block, add the new sections. The current `nav` ends with:

```yaml
  - Reading data:
    - Connections: reading-data/connections.md
    - Integrations: reading-data/integrations.md
  - Migration (2.x → 3.0): migration.md
  - Troubleshooting: troubleshooting.md
  - Changelog: changelog.md
```

Replace with:

```yaml
  - Concepts:
    - Gundi data model: concepts/data-model.md
    - Payload types: concepts/payload-types.md
    - Tracing and lifecycle: concepts/tracing-lifecycle.md
  - Authentication:
    - Overview: authentication/overview.md
    - Client credentials: authentication/client-credentials.md
    - Password grant: authentication/password-grant.md
    - OIDC discovery: authentication/oidc-discovery.md
    - Refresh and errors: authentication/refresh-and-errors.md
  - Reading data:
    - Connections: reading-data/connections.md
    - Integrations: reading-data/integrations.md
    - Routes: reading-data/routes.md
    - Traces: reading-data/traces.md
  - Sending data:
    - Observations: sending-data/observations.md
    - Events: sending-data/events.md
    - Messages and attachments: sending-data/messages-attachments.md
  - Recipes:
    - Pagination: recipes/pagination.md
    - Filtering: recipes/filtering.md
    - Custom HTTPX client: recipes/custom-httpx.md
    - Error handling: recipes/error-handling.md
  - API reference:
    - Overview: api-reference/index.md
    - GundiClient: api-reference/gundi-client.md
    - GundiDataSenderClient: api-reference/data-sender-client.md
    - auth: api-reference/auth.md
    - errors: api-reference/errors.md
  - Migration (2.x → 3.0): migration.md
  - Troubleshooting: troubleshooting.md
  - Changelog: changelog.md
```

**IMPORTANT:** The "Concepts" section was previously a single-line entry `- Concepts:` with one child. Replace the entire existing `Concepts:` block (not just append). Same for the new sub-sections you're inserting before Migration.

### Step 4: Verify the config is valid

- [ ] Run:

```bash
mkdocs build --strict
```

Expected: the build will fail with "not found" warnings for every nav target you haven't created yet (Concepts payload-types, all of Sending data, etc.). **What you DON'T want to see:** YAML parse errors or mkdocstrings configuration errors. If you see those, fix them.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml mkdocs.yml
git commit -m "docs: wire up mkdocstrings-python and extend nav for Phase 2

Adds the Concepts payload-types/tracing pages, Reading routes/traces,
Sending data section, Recipes section, and the auto-generated API
reference section. nav entries point to files that will be created in
the subsequent tasks."
```

---

## Task 4: Concepts pages

**Files:**
- Create: `docs/concepts/payload-types.md`
- Create: `docs/concepts/tracing-lifecycle.md`

### Page 4a: `docs/concepts/payload-types.md`

Required sections (H2):

1. **Three payload types** — set up the table below.
2. **Observation** — what it is, when to send one, required-ish fields (`source`, `type=tracking-device|stationary-object|gps-radio-collar|...`, `recorded_at`, `location.lat/lon`, `additional`). Cross-link to [Sending Observations](../sending-data/observations.md).
3. **Event** — what it is, when to send one, required-ish fields (`event_type`, `time`, `location.lat/lon`, `event_details`, `title`). Cross-link to [Sending Events](../sending-data/events.md).
4. **Message** — what it is (a text annotation, often attached to an event), required-ish fields (`text`, `recipient`, `sender`, plus optional `event_id`). Cross-link to [Sending Messages and Attachments](../sending-data/messages-attachments.md).
5. **Side-by-side comparison** — a table:

   | Aspect | Observation | Event | Message |
   |---|---|---|---|
   | Has a location | Yes (required) | Yes (required) | No |
   | Has a time | `recorded_at` | `time` | implicit (sent-at) |
   | Sent in batches | Yes (`List[dict]`) | Yes (`List[dict]`) | Yes (`List[dict]`) |
   | Common source | Telemetry / sensors | Operator-entered incidents | Comms / context |

6. **What gets routed where** — Brief note: all three flow through the same routing rules. A Route can transform any of them via its JQ configuration.

Required cross-references:
- → `concepts/data-model.md` (the Integration/Connection/Route vocabulary)
- → `sending-data/observations.md`, `sending-data/events.md`, `sending-data/messages-attachments.md`

Voice: same as Phase 1 concept pages. Concise, third-person, no exclamation marks.

### Page 4b: `docs/concepts/tracing-lifecycle.md`

Required sections (H2):

1. **How a payload moves through Gundi** — narrative:
   1. Provider Integration produces an Observation/Event/Message (webhook in, pull action, or `GundiDataSenderClient.post_*`).
   2. Gundi assigns an internal ID (`object_id`).
   3. Gundi looks up matching Connection(s) and resolves Routes.
   4. For each (Route, destination) pair, Gundi transforms the payload per the Route's `configuration` (often a JQ filter) and forwards.
   5. Gundi records a `Trace` for each provider → destination edge.

2. **The Trace record** — what it captures:

   | Field | Meaning |
   |---|---|
   | `object_id` | The Gundi-side ID of the source observation/event |
   | `object_type` | Payload type discriminator |
   | `related_to` | Parent object ID (e.g. for messages attached to an event) |
   | `data_provider` | Provider Integration ID |
   | `destination` | Destination Integration ID |
   | `delivered_at` | When the payload reached the destination |
   | `external_id` | The ID assigned by the destination (e.g. an EarthRanger event UUID) |
   | `created_at` / `updated_at` | Trace timestamps |
   | `last_update_delivered_at` | Time of the most recent successful update |
   | `is_duplicate` | True if Gundi suppressed this as a duplicate |
   | `has_error` | True if delivery errored |

3. **When to read traces** — diagnosing why a payload didn't reach a destination, confirming delivery, finding the destination's external ID for a Gundi observation.

Required cross-references:
- → `concepts/data-model.md`
- → `reading-data/traces.md`

### Implementation

- [ ] **Step 1: Write `docs/concepts/payload-types.md`** following the section outline above.
- [ ] **Step 2: Write `docs/concepts/tracing-lifecycle.md`** following the section outline above.

- [ ] **Step 3: Build to verify**

```bash
mkdocs build --strict 2>&1 | head -20
```

Expected: fewer "not found" warnings than before; neither of the two new files appears in them.

- [ ] **Step 4: Commit each file separately**

```bash
git add docs/concepts/payload-types.md
git commit -m "docs: add Concepts page on Observations vs Events vs Messages"

git add docs/concepts/tracing-lifecycle.md
git commit -m "docs: add Concepts page on tracing and payload lifecycle"
```

---

## Task 5: Reading Routes and Traces pages

**Files:**
- Create: `docs/reading-data/routes.md`
- Create: `docs/reading-data/traces.md`

### Page 5a: `docs/reading-data/routes.md`

A **Route** maps provider Integrations to destination Integrations, with optional payload transformations.

Required sections (H2):

1. **Method summary table:**

   | Method | Returns | Notes |
   |---|---|---|
   | `get_routes(params=None)` | `List[Route]` | First page only. |
   | `get_route_details(route_id)` | `Route` | Fetches by ID. |
   | `get_routes_for_connection(connection_id)` | `List[Route]` | Convenience wrapper for `get_routes(params={"provider": connection_id})`. |
   | `create_route(data)` | `Route` | POST. |
   | `update_route(route_id, data)` | `Route` | PATCH (partial updates supported). |
   | `delete_route(route_id)` | `None` | DELETE; returns None on success. |

2. **List routes** — `async with GundiClient()` + `get_routes()`. Include a code example printing `id`, `name`, and `len(data_providers)`.

3. **Filtering** — `params={"provider": ...}`, `params={"destination": ...}`, `params={"owner": ...}`. Note that `get_routes_for_connection(connection_id)` is the same as `get_routes(params={"provider": str(connection_id)})`.

4. **Create a route** — Example payload:

   ```python
   route = await client.create_route(data={
       "name": "TrapTagger → ER (events)",
       "owner": "<organization-id>",
       "data_providers": ["<provider-integration-id>"],
       "destinations": ["<destination-integration-id>"],
   })
   print(route.id)
   ```

5. **Update a route** — `update_route(route_id, data={"name": "Renamed"})` — PATCH allows partial dicts.

6. **Delete a route** — `await client.delete_route(route_id)`; returns None on 204.

7. **The Route model** — field table:

   | Field | Type | Description |
   |---|---|---|
   | `id` | `UUID` | Route ID |
   | `name` | `str` | Human-readable name |
   | `owner` | `Optional[UUID]` | Organization ID |
   | `data_providers` | `List[ConnectionIntegration]` | Provider Integrations |
   | `destinations` | `List[ConnectionIntegration]` | Destination Integrations |
   | `configuration` | `RouteConfiguration` | Transformation rules (often a JQ filter) |
   | `additional` | `Dict[str, Any]` | Free-form extras |

Required cross-references:
- → `concepts/data-model.md`
- → `connections.md`, `integrations.md`

### Page 5b: `docs/reading-data/traces.md`

Required sections (H2):

1. **Method summary** — just `get_traces(params)`. Returns `List[GundiTrace]`, first page only.

2. **Listing traces** — Example:

   ```python
   async with GundiClient() as client:
       traces = await client.get_traces(params={
           "object_id": "<gundi-observation-id>",
       })
       for t in traces:
           print(t.object_id, "→", t.destination, t.delivered_at)
   ```

3. **Common filters** — `object_id`, `destination_id` (or `destination` — depends on API version; flag this), `data_provider`, `has_error=true`, time range filters if the deployment supports them.

4. **The Trace model** — same field table as in `tracing-lifecycle.md` (DRY — link to that page's table instead of duplicating, OR duplicate if mkdocs-snippets aren't being used yet for this kind of include).

   For now, duplicate the field table here for self-contained reading. The Concepts page is the "why"; this page is the "how".

5. **Use cases** — three short examples:
   - Confirm a specific observation was delivered: filter by `object_id`.
   - Find errors for a destination: filter by `destination` + `has_error=true`.
   - Look up the destination's external ID for a Gundi observation: filter by `object_id`, read `external_id`.

Required cross-references:
- → `concepts/tracing-lifecycle.md`

### Implementation

- [ ] **Step 1: Write `docs/reading-data/routes.md`** following the outline.
- [ ] **Step 2: Write `docs/reading-data/traces.md`** following the outline.

- [ ] **Step 3: Build to verify**

```bash
mkdocs build --strict 2>&1 | head -20
```

- [ ] **Step 4: Commit each file separately**

```bash
git add docs/reading-data/routes.md
git commit -m "docs: add Reading Routes page (list/details/create/update/delete)"

git add docs/reading-data/traces.md
git commit -m "docs: add Reading Traces page"
```

---

## Task 6: Sending Observations page

**Files:**
- Create: `docs/sending-data/observations.md`

This is the foundational sending-data page — the patterns it establishes (auth via API key, batch shape, response format, error handling) carry over to events and messages.

Required sections (H2):

1. **Prerequisites** — to send observations you need an **Integration API key** for a provider Integration. Cross-link to `reading-data/integrations.md` (`get_integration_api_key`).

2. **Minimal example:**

   ```python
   import asyncio
   from gundi_client_v2 import GundiClient, GundiDataSenderClient


   async def main():
       async with GundiClient() as portal:
           api_key = await portal.get_integration_api_key(
               integration_id="<your-provider-integration-id>"
           )

       async with GundiDataSenderClient(integration_api_key=api_key) as sender:
           response = await sender.post_observations(data=[
               {
                   "source": "device-001",
                   "type": "tracking-device",
                   "subject_type": "wildlife.elephant",
                   "recorded_at": "2026-06-01T12:34:56Z",
                   "location": {"lat": -1.234, "lon": 36.789},
                   "additional": {"battery_voltage": 3.9},
               },
           ])
           print(response)


   asyncio.run(main())
   ```

   **Note:** `GundiDataSenderClient` does not require an async context manager — it has no session to manage between calls. Using `async with` is harmless and consistent with `GundiClient`, but a one-shot `await sender.post_observations(...)` works too.

3. **Sending multiple observations in one call** — pass a list. The API accepts batches; document that very large batches may hit per-deployment rate limits (no fixed number; consult your deployment).

4. **Required and common fields** — table:

   | Field | Required | Notes |
   |---|---|---|
   | `source` | Yes | Device identifier — typically the source's ID at the provider |
   | `type` | Yes | `tracking-device`, `stationary-object`, `ranger-radio-position`, etc. |
   | `recorded_at` | Yes | ISO-8601 timestamp |
   | `location` | Yes | `{"lat": float, "lon": float}` |
   | `subject_type` | Recommended | Helps the destination categorize |
   | `additional` | Optional | Free-form dict of additional attributes |

   Note: the exact schema for `data` is defined by the destination — Gundi forwards what it's given (potentially through a Route's transformation). When in doubt, consult the destination's API documentation (e.g. EarthRanger's `/api/v2.0/observations/`).

5. **The response** — `post_observations` returns the raw JSON the API returned. Typically a dict with a `results` array containing one entry per posted observation, each with the assigned Gundi `object_id`. Document that the exact shape can vary by deployment version.

6. **Error handling** — wrap calls in `try/except GundiAPIError`. Cross-link to `recipes/error-handling.md`. Note that `GundiDataSenderClient` uses a fixed 120-second HTTPX timeout — for very large batches you may need to split the data.

Required cross-references:
- → `reading-data/integrations.md` (for `get_integration_api_key`)
- → `concepts/payload-types.md`
- → `sending-data/events.md`, `sending-data/messages-attachments.md`
- → `recipes/error-handling.md`

### Implementation

- [ ] **Step 1: Write the page** following the outline.

- [ ] **Step 2: Build to verify**

```bash
mkdocs build --strict 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
git add docs/sending-data/observations.md
git commit -m "docs: add Sending Observations page"
```

---

## Task 7: Sending Events and Messages/Attachments pages

**Files:**
- Create: `docs/sending-data/events.md`
- Create: `docs/sending-data/messages-attachments.md`

### Page 7a: `docs/sending-data/events.md`

Mirror the Observations page structure, swapping in event-specific details.

Required sections (H2):

1. **Prerequisites** — same as Observations (API key).

2. **Minimal example:**

   ```python
   async with GundiDataSenderClient(integration_api_key=api_key) as sender:
       response = await sender.post_events(data=[
           {
               "event_type": "wildlife_sighting",
               "time": "2026-06-01T12:34:56Z",
               "location": {"latitude": -1.234, "longitude": 36.789},
               "title": "Elephant near camp",
               "event_details": {
                   "species": "African elephant",
                   "count": 3,
               },
           },
       ])
       print(response)
   ```

3. **Common event fields** — table covering `event_type`, `time`, `location`, `title`, `event_details`, `priority`, `state`.

4. **Updating an existing event** — `update_event(event_id, data={...})` (PATCH). Use the `external_id` from a Trace to get the destination's view; use the Gundi-side `object_id` to talk to Gundi.

   ```python
   updated = await sender.update_event(
       event_id="<gundi-event-object-id>",
       data={"state": "resolved"},
   )
   ```

5. **Sending event attachments** — brief mention, link to `messages-attachments.md`.

6. **Error handling** — same pattern as Observations.

### Page 7b: `docs/sending-data/messages-attachments.md`

Required sections (H2):

1. **Two distinct operations** — messages (text) and attachments (binary). Different methods, different payload shapes.

2. **Sending a message:**

   ```python
   async with GundiDataSenderClient(integration_api_key=api_key) as sender:
       response = await sender.post_messages(data=[
           {
               "sender": "ranger-1",
               "recipient": "ops-channel",
               "text": "Camera trap triggered at site B.",
               "event_id": "<optional-gundi-event-object-id>",
           },
       ])
   ```

3. **Sending an attachment** — uses `post_event_attachments(event_id, attachments)`. Each attachment is a `(filename, file_binary)` tuple:

   ```python
   with open("photo.jpg", "rb") as f:
       binary = f.read()

   async with GundiDataSenderClient(integration_api_key=api_key) as sender:
       response = await sender.post_event_attachments(
           event_id="<gundi-event-object-id>",
           attachments=[("photo.jpg", binary)],
       )
   ```

   Multiple attachments in one call: pass a list of tuples.

4. **What gets sent on the wire** — multipart form upload. Each tuple becomes a `file` form field with the given filename.

5. **Limits** — `GundiDataSenderClient` uses a fixed 120-second HTTPX timeout. Very large files may need to be split into smaller events or uploaded out-of-band and referenced by URL in the event itself.

### Implementation

- [ ] **Step 1: Write `docs/sending-data/events.md`** following the outline.
- [ ] **Step 2: Write `docs/sending-data/messages-attachments.md`** following the outline.

- [ ] **Step 3: Build to verify**

```bash
mkdocs build --strict 2>&1 | head -20
```

- [ ] **Step 4: Commit each file separately**

```bash
git add docs/sending-data/events.md
git commit -m "docs: add Sending Events page"

git add docs/sending-data/messages-attachments.md
git commit -m "docs: add Sending Messages and Attachments page"
```

---

## Task 8: Recipes — Pagination and Filtering

**Files:**
- Create: `docs/recipes/pagination.md`
- Create: `docs/recipes/filtering.md`

### Page 8a: `docs/recipes/pagination.md`

Two patterns:

1. **`get_integrations()` — async generator (handles cursor automatically)**

   ```python
   async with GundiClient() as client:
       async for integration in client.get_integrations(params={"search": "lotek"}):
           process(integration)
   ```

2. **`get_connections()` / `get_routes()` — manual pagination (returns only the first page)**

   The Gundi API uses cursor-based pagination. The exact cursor parameter name depends on the deployment (typically `cursor`, sometimes `page`). The `next` URL is returned in the raw response.

   ```python
   async with GundiClient() as client:
       all_connections = []
       params = {}
       while True:
           page = await client.get_connections(params=params)
           all_connections.extend(page)
           if len(page) < 20:  # Default page size
               break
           # Advance cursor — name depends on your deployment's API version.
           # If you need precise control, intercept the raw response or use
           # a direct HTTPX call against the connections endpoint.
           break  # placeholder — see your deployment's pagination spec
   ```

3. **Trade-offs** — eager `list()` consumes memory proportional to result count; generator allows streaming but you can't `len()` it without materializing.

### Page 8b: `docs/recipes/filtering.md`

Common patterns across the read methods:

1. **Status filters** — `params={"status": "healthy"}` works on `get_connections`. Valid values: `healthy`, `unhealthy`, `disabled`, `unknown`.

2. **Owner filters** — `params={"owner": "<organization-id>"}` works across endpoints to scope to a specific organization.

3. **Substring search** — `params={"search": "..."}` does substring match on names (when supported).

4. **Provider/destination filters on Routes** — `params={"provider": "<integration-id>"}` and `params={"destination": "<integration-id>"}`.

5. **Trace filters** — `params={"object_id": "..."}` for finding traces for a specific payload, `params={"data_provider": "...", "has_error": True}` for diagnostic queries.

6. **Combining filters** — pass multiple keys in the same dict. The API treats them as AND.

7. **Client-side filtering** — when the server doesn't expose a filter you need:

   ```python
   connections = await client.get_connections()
   recent = [c for c in connections if c.provider.name.startswith("TrapTagger")]
   ```

### Implementation

- [ ] **Step 1: Write `docs/recipes/pagination.md`**.
- [ ] **Step 2: Write `docs/recipes/filtering.md`**.

- [ ] **Step 3: Build to verify**

```bash
mkdocs build --strict 2>&1 | head -20
```

- [ ] **Step 4: Commit each file**

```bash
git add docs/recipes/pagination.md
git commit -m "docs: add Recipes — Pagination"

git add docs/recipes/filtering.md
git commit -m "docs: add Recipes — Filtering"
```

---

## Task 9: Recipes — Custom HTTPX client and Error handling

**Files:**
- Create: `docs/recipes/custom-httpx.md`
- Create: `docs/recipes/error-handling.md`

### Page 9a: `docs/recipes/custom-httpx.md`

`GundiClient` doesn't accept a pre-built `httpx.AsyncClient` — it constructs its own. But it accepts kwargs that configure the internal HTTPX client:

1. **Timeouts** — `connect_timeout` and `data_timeout`:

   ```python
   client = GundiClient(
       connect_timeout=10.0,
       data_timeout=60.0,
   )
   ```

   Defaults: 3.1s connect, 20s data.

2. **Retries** — `max_http_retries`:

   ```python
   client = GundiClient(
       max_http_retries=5,
   )
   ```

   Default: 5. Sets the `retries` parameter on `httpx.AsyncHTTPTransport`. Retries apply at the transport layer (TCP-level connection retries), not 4xx/5xx HTTP retries.

3. **SSL verification** — `use_ssl`:

   ```python
   client = GundiClient(
       use_ssl=False,
   )
   ```

   Disables certificate verification. **Only use this for local development against a self-signed IdP.** Never in production.

4. **Combining options** — all kwargs can be passed in the same constructor call:

   ```python
   client = GundiClient(
       connect_timeout=10.0,
       data_timeout=60.0,
       max_http_retries=3,
   )
   ```

5. **What you can't customize** — there's no kwarg to pass a pre-built `httpx.AsyncClient` instance, a custom transport, or a proxy URL. If you need those, file an issue.

### Page 9b: `docs/recipes/error-handling.md`

Required sections (H2):

1. **The exception hierarchy:**

   ```
   GundiClientError
     ├── AuthenticationError       # OAuth/token failures
     └── GundiAPIError              # 4xx/5xx HTTP responses
   ```

2. **Catching by category:**

   ```python
   from gundi_client_v2 import GundiClient
   from gundi_client_v2.errors import (
       AuthenticationError,
       GundiAPIError,
       GundiClientError,
   )

   async def main():
       try:
           async with GundiClient() as client:
               connections = await client.get_connections()
       except AuthenticationError as e:
           # Token request failed; user credentials or client config is wrong
           ...
       except GundiAPIError as e:
           # 4xx/5xx from the Gundi API
           print(f"Status {e.status_code}, detail: {e.detail}")
       except GundiClientError as e:
           # Anything else from the library (rare)
           ...
   ```

3. **Reading `GundiAPIError.status_code` and `.detail`** — example switch:

   ```python
   except GundiAPIError as e:
       if e.status_code == 404:
           # Resource doesn't exist (or you don't have access)
           ...
       elif e.status_code == 403:
           # Permission denied
           ...
       elif e.status_code >= 500:
           # Server-side issue; consider retrying
           ...
   ```

4. **Logging useful context** — log the `status_code` and `detail`, and the URL or operation if you can determine it:

   ```python
   import logging
   logger = logging.getLogger(__name__)

   try:
       integration = await client.get_integration_details(integration_id="...")
   except GundiAPIError as e:
       logger.error(
           "Failed to fetch integration",
           extra={"status_code": e.status_code, "detail": e.detail},
       )
       raise
   ```

5. **Retry strategies** — for transient errors (5xx, network blips), wrap with a backoff library:

   ```python
   import stamina

   @stamina.retry(on=GundiAPIError, attempts=3)
   async def list_connections(client):
       return await client.get_connections()
   ```

   Be selective: don't retry 4xx errors (they won't succeed by retrying); retry only specific 5xx codes and timeouts.

6. **Cross-link:** → `authentication/refresh-and-errors.md` for token-specific error scenarios.

### Implementation

- [ ] **Step 1: Write `docs/recipes/custom-httpx.md`**.
- [ ] **Step 2: Write `docs/recipes/error-handling.md`**.

- [ ] **Step 3: Build to verify**

```bash
mkdocs build --strict 2>&1 | head -20
```

- [ ] **Step 4: Commit each file**

```bash
git add docs/recipes/custom-httpx.md
git commit -m "docs: add Recipes — Custom HTTPX client"

git add docs/recipes/error-handling.md
git commit -m "docs: add Recipes — Error handling"
```

---

## Task 10: API reference pages

**Files:**
- Create: `docs/api-reference/index.md`
- Create: `docs/api-reference/gundi-client.md`
- Create: `docs/api-reference/data-sender-client.md`
- Create: `docs/api-reference/auth.md`
- Create: `docs/api-reference/errors.md`

### `docs/api-reference/index.md`

```markdown
# API reference

Auto-generated from the in-source docstrings of `gundi_client_v2`. For
conceptual and tutorial content see the rest of the site; this section is
a method-by-method reference.

| Module | Contents |
|---|---|
| [GundiClient](gundi-client.md) | Portal/configuration API client (auth, Connections, Integrations, Routes, Traces). |
| [GundiDataSenderClient](data-sender-client.md) | Sender for Observations, Events, Messages, and Attachments using an Integration API key. |
| [auth](auth.md) | Standalone OAuth2 grant and OIDC discovery functions. |
| [errors](errors.md) | Exception hierarchy: `GundiClientError`, `AuthenticationError`, `GundiAPIError`. |
```

### `docs/api-reference/gundi-client.md`

```markdown
# GundiClient

::: gundi_client_v2.client.GundiClient
```

### `docs/api-reference/data-sender-client.md`

```markdown
# GundiDataSenderClient

::: gundi_client_v2.client.GundiDataSenderClient
```

### `docs/api-reference/auth.md`

```markdown
# auth

Standalone OAuth2 helpers. You normally don't call these directly —
`GundiClient` orchestrates them — but they're available if you need
fine-grained control.

::: gundi_client_v2.auth
    options:
      members:
        - get_access_token_client_credentials
        - get_access_token_password_grant
        - refresh_access_token
        - discover_token_endpoint
        - clear_discovery_cache
```

### `docs/api-reference/errors.md`

```markdown
# errors

Exception classes raised by the library, plus the `raise_for_status`
helper.

::: gundi_client_v2.errors
```

### Implementation

- [ ] **Step 1: Create all five files** with the content above.

- [ ] **Step 2: Build and check rendering**

```bash
mkdocs build --strict 2>&1 | tail -30
```

Expected: no warnings. The mkdocstrings plugin will populate the API ref pages by reading docstrings from the source.

- [ ] **Step 3: Spot-check the rendered API ref**

```bash
grep -E "get_connections|post_observations|GundiAPIError" site/api-reference/gundi-client/index.html site/api-reference/data-sender-client/index.html site/api-reference/errors/index.html | head -10
```

Expected: the method names appear in the rendered HTML — confirming mkdocstrings found and rendered the docstrings.

- [ ] **Step 4: Commit**

```bash
git add docs/api-reference/
git commit -m "docs: add auto-generated API reference pages via mkdocstrings"
```

---

## Task 11: Update existing pages with cross-references

**Files:**
- Modify: `docs/index.md`
- Modify: `docs/troubleshooting.md`

### `docs/index.md` — extend the "How this site is organized" table

Find the current table:

```markdown
| Section | What's there |
|---|---|
| **Getting started** | Install, set up credentials, make your first request |
| **Concepts** | Background on Gundi's data model |
| **Authentication** | Detailed coverage of the three OAuth2 flows |
| **Reading data** | How to fetch Connections and Integrations |
| **Migration** | 2.x → 3.0 upgrade guide |
| **Troubleshooting** | Common errors and fixes |
```

Replace with:

```markdown
| Section | What's there |
|---|---|
| **Getting started** | Install, set up credentials, make your first request |
| **Concepts** | Gundi's data model; payload types; how data flows |
| **Authentication** | Detailed coverage of the three OAuth2 flows |
| **Reading data** | Fetching Connections, Integrations, Routes, and Traces |
| **Sending data** | Posting Observations, Events, Messages, and Attachments |
| **Recipes** | Common patterns: pagination, filtering, retries, error handling |
| **API reference** | Auto-generated from in-source docstrings |
| **Migration** | 2.x → 3.0 upgrade guide |
| **Troubleshooting** | Common errors and fixes |
```

### `docs/troubleshooting.md` — link to the new error-handling recipe

Find the closing "Stuck?" section:

```markdown
## Stuck?

- Check the [Authentication overview](authentication/overview.md) for
  grant-selection issues.
- Check the [Migration guide](migration.md) if you recently upgraded.
- Open an issue at
  [github.com/PADAS/gundi-client/issues](https://github.com/PADAS/gundi-client/issues).
```

Insert one new bullet at the top of that list:

```markdown
## Stuck?

- Need patterns for catching exceptions and logging? See
  [Recipes → Error handling](recipes/error-handling.md).
- Check the [Authentication overview](authentication/overview.md) for
  grant-selection issues.
- Check the [Migration guide](migration.md) if you recently upgraded.
- Open an issue at
  [github.com/PADAS/gundi-client/issues](https://github.com/PADAS/gundi-client/issues).
```

### Implementation

- [ ] **Step 1: Apply both updates**.

- [ ] **Step 2: Build**

```bash
mkdocs build --strict
```

Expected: passes with zero warnings.

- [ ] **Step 3: Commit**

```bash
git add docs/index.md docs/troubleshooting.md
git commit -m "docs: cross-link Phase 2 sections from Home and Troubleshooting"
```

---

## Task 12: Verify, push, open PR

**Files:** none (workflow only)

- [ ] **Step 1: Final strict build**

```bash
mkdocs build --strict
```

Expected: zero warnings. If any survive, fix them before continuing.

- [ ] **Step 2: Run the test suite to confirm the docstring audit didn't break anything**

```bash
pytest --tb=short
```

Expected: 73 tests pass (same as Phase 1 head).

- [ ] **Step 3: Local preview**

```bash
mkdocs serve
```

Open the site at `http://127.0.0.1:8000`. Click through the new sections:
- Concepts → Payload types, Tracing and lifecycle
- Reading data → Routes, Traces
- Sending data → all three
- Recipes → all four
- API reference → all five

Verify each renders, no broken anchors, code blocks have syntax highlighting.

Stop the server with Ctrl-C.

- [ ] **Step 4: Push the branch**

```bash
git push -u origin cd/v2-docs-site-phase2
```

- [ ] **Step 5: Open the PR**

Note: Phase 1 (PR #44) may or may not be merged at this point. If it isn't, this PR's base should be `cd/v2-docs-site` (PR stacked on PR). If it is, base should be `v2`.

```bash
# Determine the base
if git ls-remote --exit-code --heads origin cd/v2-docs-site >/dev/null 2>&1; then
  BASE=cd/v2-docs-site
else
  BASE=v2
fi

gh pr create --base "$BASE" --head cd/v2-docs-site-phase2 \
  --title "docs: complete documentation site (Phase 2)" \
  --body "$(cat <<'BODY'
## Summary

Completes the gundi-client-v2 docs site. Phase 2 of the design in [the spec](https://github.com/PADAS/gundi-client/blob/cd/v2-docs-site-phase2/docs/superpowers/specs/2026-06-01-gundi-client-v2-docs-site-phase-2.md).

## What's included

- **Docstring audit** on the public surface (`client.py`, `auth.py`, `errors.py`). Google-style; no behavioral changes; tests still pass.
- **`mkdocstrings-python` plugin** wired into `mkdocs.yml`; API reference renders from in-source docstrings.
- **Two new Concepts pages:** Observations vs Events vs Messages; Tracing and lifecycle.
- **Two new Reading data pages:** Routes (full CRUD); Traces.
- **Three new Sending data pages:** Observations, Events, Messages and Attachments.
- **Four Recipes pages:** Pagination, Filtering, Custom HTTPX client, Error handling.
- **Five auto-generated API reference pages:** Overview + one each for `GundiClient`, `GundiDataSenderClient`, `auth`, `errors`.
- Updates to `index.md` and `troubleshooting.md` to cross-link the new content.

## Verification

- `mkdocs build --strict` passes with no warnings.
- `pytest` passes (73 tests).
- All API reference pages render — mkdocstrings finds and lays out the docstrings.

## Plan

[`docs/superpowers/plans/2026-06-01-gundi-client-v2-docs-site-phase-2.md`](https://github.com/PADAS/gundi-client/blob/cd/v2-docs-site-phase2/docs/superpowers/plans/2026-06-01-gundi-client-v2-docs-site-phase-2.md)
BODY
)"
```

- [ ] **Step 6: Print the PR URL**

```bash
gh pr view --json url -q .url
```

---

## Self-review checklist

After all tasks above are complete, run this check before merging:

- [ ] **Spec coverage:** every page in the spec's content list is present.
- [ ] **No placeholders:** no "TBD", "TODO", "coming soon" in any page.
- [ ] **Internal links:** every relative link resolves. `mkdocs build --strict` catches these.
- [ ] **Code examples are runnable:** every Python example imports the names it uses.
- [ ] **Cross-references:** every "See also" / forward link in a page points to a real, written page.
- [ ] **API ref renders:** spot-check that each of the five API ref pages has actual content from the docstrings, not just an empty `:::` placeholder.
- [ ] **Docstring audit is non-behavioral:** `pytest` passes without modification.
- [ ] **Workflow triggers:** `.github/workflows/docs.yml` triggers on this PR's merge (path filter includes `docs/**`, `mkdocs.yml`, `pyproject.toml`).

## Deferred to a Phase 3 (or later)

- Versioned docs (mike)
- Webhook receiver documentation
- gundi-core schema documentation
- More recipes as users ask for them
