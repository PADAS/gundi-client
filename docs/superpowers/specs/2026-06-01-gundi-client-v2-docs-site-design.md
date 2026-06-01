# gundi-client-v2 docs site design

**Status:** approved
**Date:** 2026-06-01
**Owner:** Chris Doehring

## Problem

Third-party developers building apps and utilities on top of Gundi keep asking
how to use `gundi-client-v2`. Today the only learning resources are the
`README.md`, the `examples/` directory, and the source code itself. None of
these are discoverable through search, none version cleanly, and the examples
cover only a thin slice (the three auth paths against `get_connections`).

## Goals

- A dedicated documentation site hosted on GitHub Pages, modeled on the
  `earthranger-smart-utils` (er-smart-sync) docs.
- Cover the full library surface for developers, not the SDK internals.
- Auto-generated API reference so it stays in sync with the code.
- A clear migration story (2.x → 3.0) reachable from the site.

## Non-goals

- A user-facing "how Gundi works" portal — that belongs at gundiservice.org.
- API surface design changes to the library itself. If a docstring is missing
  or unclear we will improve it, but no behavioral changes.
- Versioned docs (mike). Postpone until we have a second major version live;
  for now the site reflects the latest published release.
- A CLI reference section — `gundi-client-v2` ships no CLI.

## Audience

Python developers building third-party apps or utilities against Gundi. They
know async Python and HTTP-shaped APIs but not necessarily Gundi's domain
model. We do not assume familiarity with Keycloak, OIDC, or PADAS-internal
conventions.

## Site infrastructure

- **MkDocs Material** theme. Same plugin set as er-smart-sync: search,
  pymdownx (highlight, tabbed, superfences, details, snippets), admonitions,
  attr_list, tables, toc.
- **mkdocstrings-python** plugin for the API reference section. Read from
  the library source on the same branch.
- **GitHub Pages** deployment. URL: `https://padas.github.io/gundi-client/`
  (the repo is `PADAS/gundi-client`, even though the package is named
  `gundi-client-v2`).
- **GitHub Actions** workflow at `.github/workflows/docs.yml` deploys on push
  to `v2`. Uses the official `actions/deploy-pages` flow.
- `mkdocs.yml` at repo root. Content under `docs/`. The existing
  `docs/superpowers/` tree (specs, plans) is excluded from the published site
  via the mkdocs `exclude` plugin glob, same as er-smart-sync.
- A new `[dependency-groups] docs` group in `pyproject.toml` for mkdocs and
  its plugins. Doesn't affect the runtime install.

## Nav structure

```
Home (index.md)
Getting started
  - Installation
  - Authentication setup
  - First request
Concepts
  - Gundi data model
  - Observations vs Events vs Messages
  - Tracing and lifecycle
Authentication
  - Overview of the three auth paths
  - Client credentials (M2M)
  - Password grant (user-facing)
  - OIDC discovery
  - Refresh tokens and error handling
Reading data
  - Connections
  - Integrations
  - Routes
  - Traces
Sending data
  - Observations
  - Events
  - Messages and attachments
Recipes
  - Pagination
  - Filtering connections/integrations
  - Custom HTTPX client (timeouts, retries)
  - Error handling and logging
API reference (auto-generated)
  - GundiClient
  - GundiDataSenderClient
  - auth functions
  - errors
  - schemas (link out to gundi-core)
Migration (2.x → 3.0)
Troubleshooting
Changelog (link to GitHub releases)
```

## Content responsibility

| Source | Pages |
|---|---|
| Hand-written | Home, Getting started, Concepts, Authentication, Reading data, Sending data, Recipes, Troubleshooting |
| Auto-generated (mkdocstrings) | API reference |
| Copied from existing files | Migration (renders `MIGRATION.md` via `pymdownx.snippets`) |
| Link out | Changelog (GitHub Releases page) |

## Phase split

The full nav above is the target for this work. Ship in two PRs to get
something live without blocking on docstring quality:

**Phase 1 — first PR**

- Site scaffolding (`mkdocs.yml`, GitHub Actions, dependency group)
- Pages: Home, Installation, Authentication setup, First request,
  Gundi data model, all four Authentication pages, Reading Connections,
  Reading Integrations, Migration
- ~13 pages. Covers the immediately-requested scope (intro + read
  Connections/Integrations) plus the auth foundation everything else
  depends on.

**Phase 2 — second PR**

- Pages: Observations vs Events vs Messages, Tracing and lifecycle, Reading
  Routes, Reading Traces, all of Sending data, all of Recipes, API reference,
  Troubleshooting, Changelog link
- Requires a docstring audit on `client.py` for the auto-generated API
  reference. Improve docstrings as we go; no behavior changes.

## Open questions / risks

- **Custom domain for the docs site.** Default is
  `padas.github.io/gundi-client/`. If marketing wants `docs.gundiservice.org`
  or similar, that's a small DNS + GitHub Pages config follow-up — not in
  scope for either phase.
- **Multi-language SDK?** Some users have asked about a JS client. Out of
  scope; the docs are for the Python client. We name the site
  "gundi-client-v2 (Python)" to keep the door open.
- **gundi-core schema docs.** Many response shapes are defined in
  `gundi-core`. We link out rather than duplicate. If gundi-core ever ships
  its own docs site we cross-link; until then, schemas are summarized inline
  where they matter for a given page.
- **Docstring quality.** Auth docstrings are already good; client.py needs
  an audit. Phase 2 absorbs that work; we don't block Phase 1 on it.

## Success criteria

- Site is reachable at the hosted URL, search works, code samples have a
  one-click copy button.
- A developer who has never touched Gundi can install the library, configure
  auth, and list Connections within 15 minutes by following Getting started.
- The migration page is the first hit when a maintainer of one of the 30+
  consumer repos searches for "gundi-client-v2 3.0 upgrade".
