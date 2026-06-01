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
| **Concepts** | Gundi's data model; payload types; how data flows |
| **Authentication** | Detailed coverage of the three OAuth2 flows |
| **Reading data** | Fetching Connections, Integrations, Routes, and Traces |
| **Sending data** | Posting Observations, Events, Messages, and Attachments |
| **Recipes** | Common patterns: pagination, filtering, retries, error handling |
| **API reference** | Auto-generated from in-source docstrings |
| **Migration** | 2.x → 3.0 upgrade guide |
| **Troubleshooting** | Common errors and fixes |
