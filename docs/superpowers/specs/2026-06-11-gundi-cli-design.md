# Gundi CLI — Design

**Date:** 2026-06-11
**Status:** Approved (pending spec review)
**Repo:** `gundi-client` (`gundi-client-v2` package, `v2` branch)

## Summary

Add a small command-line interface to the `gundi-client-v2` package for two
operations against the Gundi API:

1. **List integrations**, optionally filtered by integration type.
2. **Enable / disable** an integration (toggle its `enabled` flag).

The CLI is a thin wrapper over the existing async `GundiClient`. It ships with
the package as an installable `gundi` console command, behind an optional
dependency extra so the core SDK stays dependency-lean.

## Goals / Non-goals

**Goals**
- One installable entry point (`gundi`) exposing the two operations.
- Reuse the SDK's existing client methods and env-var-based auth verbatim.
- Human-readable output by default, machine-readable (`--json`) on demand.
- Clean error messages and exit codes (no raw tracebacks for expected failures).

**Non-goals (YAGNI for v1)**
- No CRUD beyond the enabled flag (no create/delete, no config edits).
- No filtering by multiple types at once (single `--type` only).
- No interactive integration picker / name-search resolution (UUID only).
- No commands for other nouns (routes, connections) — structure allows them later.

## Command surface

```
gundi integrations list [--type SLUG] [--json]
gundi integrations enable  <integration-id>
gundi integrations disable <integration-id>
```

A nested `integrations` command group is used so future nouns can be added
without restructuring the CLI.

### `integrations list`
- Calls `client.get_integrations(params=...)`, which is an async generator that
  auto-paginates across all result pages.
- `--type SLUG` → forwarded as `params={"type": slug}`. Single value only. When
  omitted, no `params` are sent (all integrations).
- **Default output:** a plain-text aligned table with columns:
  `ID  NAME  TYPE  ENABLED  STATUS`
  - `TYPE` renders the integration type slug/value (`integration.type.value`).
  - `ENABLED` renders as `true` / `false`.
- `--json` → emits `json.dumps([i.dict() for i in integrations], default=str, indent=2)`
  (UUIDs/datetimes serialized as strings), suitable for piping to `jq`.
- Empty result set prints a short `No integrations found.` to stderr (table mode)
  or `[]` (json mode), exit code 0.

### `integrations enable` / `integrations disable`
- Two explicit subcommands (not one `--enabled/--disabled` flag) for clarity and
  safety.
- Each wraps `client.update_integration(integration_id, {"enabled": True|False})`.
- Target identified by **UUID only** — explicit and unambiguous.
- `update_integration` already re-fetches and returns the updated `Integration`;
  print a one-line confirmation reflecting the resulting state, e.g.
  `Integration <id> (<name>) is now disabled.`
- No interactive confirmation prompt: the subcommand name is the intent and the
  change is reversible.

## Structure & packaging

New package `gundi_client_v2/cli/`:

| File | Purpose |
|------|---------|
| `gundi_client_v2/cli/__init__.py` | Typer `app`, the `integrations` sub-app wiring, `build_client()` auth helper, and an `ImportError` guard with a friendly install hint. |
| `gundi_client_v2/cli/integrations.py` | The `list` / `enable` / `disable` commands and table-rendering helper. |

`pyproject.toml` changes:
- Add optional extra:
  ```toml
  [project.optional-dependencies]
  cli = ["typer>=0.12"]
  ```
- Add console entry point:
  ```toml
  [project.scripts]
  gundi = "gundi_client_v2.cli:app"
  ```

Typer is imported **only inside** `gundi_client_v2/cli/`, so `import gundi_client_v2`
never requires it. If the `gundi` command is invoked without the `cli` extra
installed, the entry point's import fails — `cli/__init__.py` catches `ImportError`
on the `typer` import and prints:
`Error: the 'gundi' CLI requires extra dependencies. Install with: pip install "gundi-client-v2[cli]"`
then exits non-zero.

## Auth / configuration

- A single `build_client()` helper reads environment variables and constructs
  `GundiClient(**kwargs)`, mirroring the `examples/` auth patterns:
  - Required: `GUNDI_API_BASE_URL`, `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`.
  - Token endpoint — at least one of: `OAUTH_ISSUER` (preferred; the client
    resolves the token endpoint via OIDC discovery, IdP-agnostic) or
    `OAUTH_TOKEN_URL` (explicit). When both are set, the explicit URL wins.
  - Optional: `OAUTH_AUDIENCE` (passed through when set; required by some IdPs).
- `environs` (already a core dependency) loads a `.env` file from the working
  directory for local convenience.
- Missing required vars → print `Error: missing required env vars: <list>` to
  stderr and exit code **2**.

## Async bridge & error handling

- Each Typer command is a thin **sync** function that calls `asyncio.run(...)`
  around an `async with GundiClient(...) as client:` block.
- Expected failures are caught and rendered cleanly (no traceback):
  - `AuthenticationError` and `GundiAPIError` (from `gundi_client_v2`) → print
    `Error: <message>` to stderr, `raise typer.Exit(1)`.
  - Missing env config → exit code 2 (see above).
- Unexpected exceptions are left to propagate (genuine bugs surface loudly).

### Exit codes
| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | API / auth error |
| 2 | Missing/invalid configuration (env vars) |

## Testing

`tests/test_cli.py` using Typer's `CliRunner` and `respx` (the existing dev-time
HTTP mock):

- `list` default renders a table containing expected ids/names.
- `list --json` emits valid JSON parseable back into the expected objects.
- `list --type <slug>` forwards `type=<slug>` as a query param on the request.
- `list` follows pagination (mock a two-page `next` response, assert both pages
  appear).
- `enable <id>` / `disable <id>` issue a PATCH with body `{"enabled": true/false}`
  to the correct URL.
- Missing required env var → exit code 2 with a message naming the missing var(s).
- API error (mock 4xx) → exit code 1, clean error message, no traceback.

## Open questions

None outstanding. (`--type` is single-value by decision; multi-type deferred.)
