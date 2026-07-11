---
name: using-the-gundi-cli
description: Use when inspecting or managing Gundi integrations from the terminal — listing integrations, reading an integration's activity logs to debug it, enabling/disabling an integration, or checking integration types and health status. Covers the `gundi` CLI (gundi-client-v2[cli]), its auth, and named environments.
---

# Using the Gundi CLI

## Overview

`gundi` is the command-line front end to the Gundi v2 API (backed by cdip). Use it
to list integrations, read their activity logs, toggle their `enabled` flag, and
inspect integration types — without writing a script against `GundiClient`.

Install (Typer lives in the optional `cli` extra):

```bash
pip install "gundi-client-v2[cli]"
```

## Authentication (do this first)

Every command needs a token. There are two ways to supply auth; pick one.

**A. Named environments (recommended for repeated use).** Save connection config
once, log in once, and later commands reuse a cached token. **Raw credentials
(password / client secret) are never written to disk** — but the OAuth tokens
derived from them (access *and* refresh tokens, which are themselves secrets) are
cached under `$XDG_CONFIG_HOME/gundi/tokens/` (defaults to `~/.config/gundi/tokens/`)
at mode 0600.

```bash
# Developer (password grant): include --username so login knows who you are.
gundi env add prod --base-url https://api.gundi.example.com \
  --client-id my-client --issuer https://auth.example.com/realms/prod \
  --username me@example.com
gundi env use prod                         # set active env
gundi auth login                           # prompts for the PASSWORD (hidden); reuses stored --username
gundi auth status                          # shows valid/expired
gundi integrations list                    # reuses the cached token
gundi integrations list --profile dev      # override active env per command
```

Only the **secret/password** is ever prompted. The **username is not prompted** —
it comes from the env's stored `--username`, the `--username`/`-u` flag on
`auth login`, or `GUNDI_USERNAME`. Omit all three and you get client-credentials,
not password grant. For a service env, skip `--username` and supply
`OAUTH_CLIENT_SECRET` (via env or prompt) instead.

**B. Raw env vars (good for one-offs / CI).** Export them and run. Required:
`GUNDI_API_BASE_URL`, `OAUTH_CLIENT_ID`, a token endpoint (`OAUTH_ISSUER`
preferred, or `OAUTH_TOKEN_URL`), and credentials:
- `GUNDI_USERNAME` + `GUNDI_PASSWORD` (password grant, for developers), **or**
- `OAUTH_CLIENT_SECRET` (client-credentials, for services).

A `.env` in the current directory (or a parent — it walks up) is **loaded
automatically**. To load a specific file instead, point `GUNDI_CLIENT_ENVFILE`
at its path (e.g. `GUNDI_CLIENT_ENVFILE=./dev.env gundi integrations list`); it
takes precedence over a discovered `.env`. Real environment variables always
win over both.

Selection precedence: `--profile` → `GUNDI_PROFILE` → active env → raw env vars.

## Command reference

| Command | What it does |
|---|---|
| `gundi integrations list` | Table: ID, NAME, TYPE, ENABLED, STATUS |
| `gundi integrations list --type earth_ranger` | Filter by type **slug** |
| `gundi integrations list --enabled` / `--disabled` | Filter by enabled state |
| `gundi integrations list --status healthy` | Filter by health (`healthy`/`unhealthy`/`disabled`) |
| `gundi integrations list --json` | JSON for `jq` |
| `gundi integrations types` | Table: NAME, SLUG, ID |
| `gundi integrations logs <uuid>` | Latest activity logs for one integration |
| `gundi integrations logs --type earth_ranger` | Logs across all integrations of a type |
| `gundi integrations enable <uuid>` / `gundi integrations disable <uuid>` | Toggle the enabled flag |
| `gundi env add/list/show/use/remove` | Manage named environments |
| `gundi auth login/logout/status` | Manage the cached token |

Log filters (combine freely): `--level debug|info|warning|error` (matches that
level **and above**), `--origin <exact>`, `--since` / `--until` (`YYYY-MM-DD` or
ISO 8601), `--limit N` (default 50). Run `gundi <group> --help` for full flags.

## Common workflows

**Debug a misbehaving integration** — find it, then read its errors:
```bash
gundi integrations list --type earth_ranger --status unhealthy
gundi integrations logs 338225f3-... --level error --since 2026-07-01
```

**Find an integration id from a name** (ids are UUIDs; the CLI never takes a name):
```bash
gundi integrations list --json | jq -r '.[] | select(.name=="My Site") | .id'
```

**Turn one off / back on:**
```bash
gundi integrations disable 338225f3-...
gundi integrations enable  338225f3-...
```

## Key gotchas

- **Type is a slug, integration is a UUID.** `--type earth_ranger` takes the
  slug; the CLI resolves it to the type's UUID **client-side** (an extra call to
  the types API, so an unknown slug exits 2 before anything is listed) and then
  filters server-side by that UUID. `enable`/`disable`/`logs <id>` take the
  integration's **UUID** — get it from `list`.
- **`logs` needs exactly one target:** either a positional `<uuid>` **or**
  `--type <slug>`, not both and not neither (exits 2).
- **`logs --type <slug>` is filtered server-side** in one request (the
  `/v2/logs/?integration_type=` filter) — no id-gathering. Unlike `list --type`,
  it does *not* validate the slug client-side, so an unknown/typo'd slug returns
  no logs rather than an error.
- **`logs --type` requires the server-side filter to be deployed.** It relies on
  the portal supporting `/v2/logs/?integration_type=`. An **older portal silently
  ignores the unknown param and returns _unfiltered_ logs** (all types) — so if
  `logs --type X` looks like it's returning everything, that portal predates the
  filter. There's no client-side detection (an ignored param still returns HTTP
  200), so treat unexpectedly broad `--type` output as "filter not deployed here."
- **Client-credentials grant has no refresh token.** Password-grant envs refresh
  transparently. A client-credentials env can't *refresh*, but it will
  *re-authenticate* automatically when `OAUTH_CLIENT_SECRET` is present in the
  environment at command time; without the secret, run `gundi auth login` again
  once the access token expires.
- **`auth status` reports `valid` from the cached expiry, not real acceptance.**
  It only checks the locally-stored `expires_at`; the server can still reject the
  token (a stale access token whose refresh token was already rotated). So a
  command can fail with `not authenticated` right after `auth status` says
  `valid`. Don't gate on `auth status` — just run the command, and on a `1`
  auth error run `gundi auth login` again (add `--profile <env>` to match the
  command that failed).

## Exit codes

`0` success · `1` API/auth error (clean `Error: …`, no traceback) · `2` missing
or invalid configuration (bad env, unknown **`list --type`** slug, bad
`--level`/date, etc.). Note `logs --type <unknown-slug>` is *not* an error — it
resolves server-side and returns exit `0` with no logs (assuming the
`integration_type` filter is deployed; an older portal ignores it and returns
exit `0` with *unfiltered* logs). Scripts can branch on these.
