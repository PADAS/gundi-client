# GUNDI_OAUTH_* env var prefix — design

**Date:** 2026-07-30
**Status:** Approved
**Target release:** 3.7.0 (minor; no breaking change)

## Problem

The 3.0 rename of `KEYCLOAK_*` to `OAUTH_*` made the auth env vars generic but
left them unqualified. Generic names like `OAUTH_CLIENT_ID` risk collisions with
other tools sharing an environment, and are inconsistent with the vars that
already carry the project prefix (`GUNDI_API_BASE_URL`, `GUNDI_USERNAME`,
`GUNDI_PASSWORD`, `GUNDI_CLIENT_ENVFILE`). The `OAUTH_*` names have shipped in
every 3.x release, so they cannot simply be dropped.

## Decision

The documented, preferred env var names become:

- `GUNDI_OAUTH_ISSUER`
- `GUNDI_OAUTH_TOKEN_URL`
- `GUNDI_OAUTH_CLIENT_ID`
- `GUNDI_OAUTH_CLIENT_SECRET`
- `GUNDI_OAUTH_AUDIENCE`
- `GUNDI_OAUTH_SCOPE`

Old names keep working via **silent fallback** — no deprecation warnings, no
removal planned. Docs and examples switch to the new names.

## Scope

OAuth vars only. `LOG_LEVEL` and `SENSORS_API_BASE_URL` stay unprefixed
(explicitly out of scope per user decision). No deprecation warnings. The CLI's
named-environments config file stores generic keys (`client_id`, `issuer`, …),
not env var names, and is unaffected.

## Changes

### 1. `gundi_client_v2/settings.py`

Extend each env lookup chain by one link at the front:

| Setting | Lookup chain |
|---|---|
| `OAUTH_ISSUER` | `GUNDI_OAUTH_ISSUER` → `OAUTH_ISSUER` → `KEYCLOAK_ISSUER` |
| `OAUTH_TOKEN_URL` | `GUNDI_OAUTH_TOKEN_URL` → `OAUTH_TOKEN_URL` |
| `OAUTH_CLIENT_ID` | `GUNDI_OAUTH_CLIENT_ID` → `OAUTH_CLIENT_ID` → `KEYCLOAK_CLIENT_ID` |
| `OAUTH_CLIENT_SECRET` | `GUNDI_OAUTH_CLIENT_SECRET` → `OAUTH_CLIENT_SECRET` → `KEYCLOAK_CLIENT_SECRET` |
| `OAUTH_AUDIENCE` | `GUNDI_OAUTH_AUDIENCE` → `OAUTH_AUDIENCE` → `KEYCLOAK_AUDIENCE` |
| `OAUTH_SCOPE` | `GUNDI_OAUTH_SCOPE` → `OAUTH_SCOPE` → `"openid"` |

`TOKEN_URL` and `SCOPE` have no `KEYCLOAK_*` ancestor. The module constants stay
named `OAUTH_*` (plus the existing `KEYCLOAK_*` aliases): the rename concerns
the environment interface, not the Python attribute names, and renaming the
constants would churn `client.py` and the CLI with no user-visible benefit.

### 2. CLI — `gundi_client_v2/cli/_client.py`

Add a small helper that resolves an OAuth var with the prefix preferred:
`_getenv("OAUTH_CLIENT_ID")` checks `GUNDI_OAUTH_CLIENT_ID` first, then
`OAUTH_CLIENT_ID`. Use it at every `os.environ.get("OAUTH_*")` call site
(seven sites: `_REQUIRED_ENV` handling in `build_client()`, the client-secret
reads in `build_client()`, `_build_profile_client()`, and
`build_client_for_login()`, plus issuer/token-url/audience in
`build_client()`).

The CLI chain is `GUNDI_OAUTH_*` → `OAUTH_*` only — the CLI postdates the
Keycloak rename and never accepted `KEYCLOAK_*`; that stays true.

Missing-config error messages name the new preferred form, e.g.
`GUNDI_OAUTH_CLIENT_ID` and
`GUNDI_OAUTH_CLIENT_SECRET (or GUNDI_USERNAME + GUNDI_PASSWORD)`.

### 3. Docs, examples, docstrings

Switch primary names to `GUNDI_OAUTH_*` with a one-line note that `OAUTH_*`
(and `KEYCLOAK_*` for the library) remain accepted:

- `README.md`, `MIGRATION.md`, `docs/` (getting-started, authentication,
  troubleshooting)
- `examples/*.py` and `examples/README.md`
- Docstrings in `gundi_client_v2/client.py` and `gundi_client_v2/cli/_client.py`
- `.claude/skills/using-the-gundi-cli/SKILL.md`

### 4. Tests

- `tests/client/test_settings.py`: precedence tests — `GUNDI_OAUTH_X` wins over
  `OAUTH_X`, which wins over `KEYCLOAK_X`; new names work alone.
- `tests/test_cli.py` / `tests/test_cli_auth.py`: CLI accepts `GUNDI_OAUTH_*`;
  missing-var error messages show the new names.
- Existing old-name tests stay untouched — they are the back-compat regression
  suite.

## Error handling

No new failure modes: a var missing from every link of its chain behaves
exactly as a missing var does today (library: `None` / auth error at request
time; CLI: exit 2 listing missing names).

## Release

Version bump to 3.7.0 following the existing release process.
