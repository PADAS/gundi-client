# gundi-client-v2 docs site — Phase 2 design

**Status:** approved
**Date:** 2026-06-01
**Owner:** Chris Doehring
**Builds on:** [Phase 1 design](2026-06-01-gundi-client-v2-docs-site-design.md)

## Problem

Phase 1 shipped the docs site infrastructure, the auth foundation, and the
"read Connections / Integrations" coverage. Third-party developers can now
discover the library, configure auth, and read the core resources. What
they can't yet do from the docs alone:

- Understand the differences between Observations, Events, and Messages.
- Send any data into Gundi.
- Read or manage Routes (created in 2.6/3.0).
- Read Traces for diagnostics.
- Find common patterns (pagination, custom HTTPX clients, error handling).
- Browse a complete API reference without reading the source.

Phase 2 fills these gaps.

## Goals

- Complete the user-facing documentation for `gundi-client-v2` 3.0.
- Auto-generated API reference renders cleanly via mkdocstrings-python.
- Audit and improve the docstrings on every public surface so the API
  reference is useful (not just "method exists").
- Ship as a single PR — the docstring audit and the API-reference pages
  belong together at merge time.

## Non-goals

- Behavioral changes to the library. Docstring improvements only;
  no signature changes, no new public methods.
- A Recipes section beyond four targeted patterns (pagination, filtering,
  custom HTTPX client, error handling). Other patterns can land in a
  follow-up after we see what users actually ask.
- Webhook receiver documentation. That's a server-side concern, not a
  client-library concern.
- Versioned docs. Defer until a second major version is live.
- Coverage of `gundi-core` internals beyond cross-linking to its source.

## Audience

Same as Phase 1: Python developers building third-party apps or utilities
against Gundi.

## Content to add

### Concepts (2 pages)

- **`concepts/payload-types.md`** — Observations vs Events vs Messages.
  What each payload represents, when to use which, what fields are
  required, how Gundi routes them. Sets up the Sending data section.
- **`concepts/tracing-lifecycle.md`** — How a payload moves through
  Gundi: webhook in → provider → routing → destination → trace.
  Sets up the Reading Traces page.

### Reading data (2 new pages, integrated into existing section)

- **`reading-data/routes.md`** — `get_routes()`,
  `get_route_details(route_id)`,
  `get_routes_for_connection(connection_id)`, `create_route(data)`,
  `update_route(route_id, data)`, `delete_route(route_id)`. Includes
  the `Route` model field list.
- **`reading-data/traces.md`** — `get_traces(params)`, common filter
  keys (`object_id`, `destination_id`, `destination`), `Trace` model
  fields, links to the tracing-lifecycle concept page.

### Sending data (3 pages)

- **`sending-data/observations.md`** — `GundiDataSenderClient.post_observations(data)`.
  Authentication setup (Integration API key), payload schema,
  bulk-send patterns, response handling.
- **`sending-data/events.md`** — `post_events(data)`, `update_event(event_id, data)`,
  event types and required fields.
- **`sending-data/messages-attachments.md`** — `post_messages(data)`,
  `post_event_attachments(event_id, attachments)`. Multipart upload
  handling for attachments.

### Recipes (4 pages)

- **`recipes/pagination.md`** — Walking the `next` cursor manually for
  `get_connections()` and `get_routes()`. Using `get_integrations()`
  as an async generator. The trade-off (eager list vs streaming).
- **`recipes/filtering.md`** — Common filter idioms across the
  read methods. How to combine filters. When the API supports
  server-side filtering vs when to filter client-side.
- **`recipes/custom-httpx.md`** — Setting `connect_timeout` and
  `data_timeout`. Configuring `max_http_retries`. Disabling SSL
  verification for self-signed dev IdPs (with appropriate warnings).
- **`recipes/error-handling.md`** — The exception hierarchy
  (`GundiClientError` → `GundiAPIError`, `AuthenticationError`).
  Catching specific exceptions, logging useful context, retry
  strategies. Cross-link to [Authentication → Refresh and errors](../authentication/refresh-and-errors.md).

### API reference (auto-generated)

- **`api-reference/index.md`** — Brief landing: how to navigate, what's
  here, links to the four sub-pages.
- **`api-reference/gundi-client.md`** — `::: gundi_client_v2.client.GundiClient`
- **`api-reference/data-sender-client.md`** — `::: gundi_client_v2.client.GundiDataSenderClient`
- **`api-reference/auth.md`** — `::: gundi_client_v2.auth` (the
  module-level standalone functions).
- **`api-reference/errors.md`** — `::: gundi_client_v2.errors` (the
  exception hierarchy).

### Updates to existing pages

- **`docs/index.md`** — Add the new sections to the "How this site is
  organized" table.
- **`docs/troubleshooting.md`** — Add a section linking to
  Recipes → Error handling once that page exists.

## Infrastructure changes

- Add `mkdocstrings[python]>=0.24` to the `[project.optional-dependencies]
  docs` group in `pyproject.toml`.
- Add `mkdocstrings` to the `plugins` list in `mkdocs.yml`, configured to
  read from the local `gundi_client_v2/` package and use Google-style
  docstring parsing.
- Update the `nav` in `mkdocs.yml` with the new sections in the order
  established by the Phase 1 design.

## Docstring audit

Cover these public surfaces with Google-style docstrings consistent enough
for mkdocstrings to render cleanly:

**`gundi_client_v2/client.py`** — all public methods on `GundiClient` and
`GundiDataSenderClient`. Existing terse docstrings get expanded; missing
ones get added. Cover `Args`, `Returns`, `Raises`, and a one-line summary
at the top.

**`gundi_client_v2/auth.py`** — standalone functions
(`get_access_token_client_credentials`, `get_access_token_password_grant`,
`refresh_access_token`, `discover_token_endpoint`, `clear_discovery_cache`).
Most already have good docstrings; verify they render and tighten where
needed.

**`gundi_client_v2/errors.py`** — exception classes
(`GundiClientError`, `GundiAPIError`, `AuthenticationError`). One-line
class docstrings minimum; cover `__init__` args (`status_code`, `detail`)
where present.

Non-goals for the audit: internal helpers (`_post_token`, `_get`, `_post`,
`_refresh_token`, etc.), the settings module (env vars are documented in
the prose pages, not in the API reference).

## Phasing within Phase 2

Single PR. Internally batched into checkpoints for the subagent-driven
execution flow:

1. Docstring audit on `client.py`
2. Docstring audit on `auth.py` and `errors.py`
3. mkdocstrings wiring (pyproject, mkdocs.yml plugin + nav)
4. Concepts pages (2)
5. Reading Routes + Traces (2)
6. Sending Observations + Events + Messages/Attachments (3)
7. Recipes (4)
8. API reference scaffolding (5 mkdocstrings pages)
9. Updates to existing pages (index, troubleshooting cross-link)
10. Strict build + verification + PR open

## Open questions / risks

- **`Trace` model fields.** Need to confirm shape from `gundi-core` —
  the `get_traces` examples in the codebase pass `object_id` and
  `destination_id`/`destination` as filter keys, so those at least exist.
  Full field list needs verification.
- **Bulk send patterns.** `post_observations` accepts `List[dict]` — we
  should document any size limits (server-side rate limits, max-batch
  size, etc.). If we don't know them precisely, document "send in
  reasonable batches; check your Gundi deployment for rate limits."
- **Attachment formats.** `post_event_attachments` takes
  `List[tuple]` — needs verification: probably `(filename, file_obj)`
  or `(filename, bytes)`. Read the source to confirm before documenting.
- **mkdocstrings cross-references.** If a docstring on `GundiClient.get_connections`
  mentions `Connection`, can mkdocstrings auto-link it to the
  `gundi-core` schema? Probably not without configuring an inventory.
  Acceptable to leave unlinked for now; document the type in prose.

## Success criteria

- `mkdocs build --strict` passes with zero warnings on the new branch.
- A developer reading the site can:
  1. Understand the Observations vs Events vs Messages distinction
     without leaving the docs.
  2. Send an observation end-to-end from `Authentication setup` →
     `Sending Observations`.
  3. Manage Routes for a Connection using only the docs.
  4. Find an explanation for any error in `GundiClientError`'s hierarchy.
- The API reference shows every public method with its signature, args,
  return type, and a useful summary line.
- The docstring audit changes are non-behavioral (verified by tests
  passing without modification).
