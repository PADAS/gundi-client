# Gundi CLI — Named Environments + Token Cache

**Date:** 2026-06-12
**Status:** Approved (pending spec review)
**Repo:** `gundi-client` (`gundi-client-v2` package, `v2` branch)
**Builds on:** `2026-06-11-gundi-cli-design.md` (the base CLI)

## Summary

Add persistent, named **environments** to the `gundi` CLI (a "default" plus
user-added ones like `dev`, `prod`, `stage`) and a **cross-invocation token
cache** so repeat commands don't re-run the OAuth round-trip every time.

Modeled loosely on `gcloud`: an environment is a named bundle of *non-secret*
connection config; authentication produces a cached token that subsequent
commands reuse. **Secrets are never written to disk** — only the OAuth tokens
derived from them.

> **Terminology:** "environment" and "profile" refer to the same thing. The
> management commands are `gundi env …`; the per-command override is
> `--profile <name>` / `GUNDI_PROFILE` (kept for familiarity and because "env"
> as a flag would collide with the notion of OS environment variables).

## Goals / Non-goals

**Goals**
- Store named environments (connection config) and switch the active one.
- Avoid re-authenticating on every command by caching the OAuth token between
  invocations and refreshing it transparently when possible.
- Keep secrets off disk; keep the current raw-env-var workflow working.
- No new runtime dependencies (JSON via stdlib).

**Non-goals (YAGNI)**
- No storing of `client_secret` / `password` at rest (file or keyring).
- No interactive browser/device auth flows — credentials come from env or a
  hidden prompt at login time.
- No multi-user/shared config; this is per-user local config.

## Storage layout

XDG-based, under `XDG_CONFIG_HOME` (default `~/.config`):

```
~/.config/gundi/config.json          # dir mode 0700, file mode 0600
  {
    "active": "prod",
    "environments": {
      "prod": {
        "base_url": "https://api.gundi.example.com",
        "client_id": "my-client",
        "issuer": "https://auth.example.com/realms/prod",   # or "token_url"
        "audience": "my-audience",        # optional
        "username": "dev@example.com",    # optional (non-secret)
        "scope": "openid"                 # optional
      },
      "dev": { ... }
    }
  }

~/.config/gundi/tokens/<env>.json     # file mode 0600, one per environment
  {
    "access_token": "...",
    "refresh_token": "...",
    "token_type": "Bearer",
    "expires_at": "2026-06-12T18:30:00+00:00",          # absolute ISO 8601
    "refresh_expires_at": "2026-06-13T06:00:00+00:00"   # absolute ISO 8601
  }
```

- **Format:** JSON (stdlib `json`; no TOML/YAML/INI dependency).
- **Secrets:** `client_secret` and `password` are **never** persisted. Only
  the derived OAuth tokens are cached.
- **Permissions:** config dir created `0700`; `config.json` and token files
  written `0600`. Per-environment token files mean `logout` is a file delete
  and switching environments never clobbers another's token.

## Authentication model

### Grant types and refresh (accepted tradeoff)
- **Password grant** (developer flow): `auth login` yields an **access + refresh**
  token. When the access token expires, the client renews it via the
  refresh-token grant — no password required. Long-lived, smooth.
- **Client-credentials**: IdPs typically issue **no refresh token**. The cached
  access token is reused until expiry; once expired, because no secret is
  stored, the command reports *session expired — run `gundi auth login`*. This
  is the accepted cost of not storing secrets.

### Where secrets come from at login
`gundi auth login` needs the secret for the active environment's grant:
- Password grant: `GUNDI_PASSWORD` from env, else a hidden prompt. Username comes
  from the environment config (or `GUNDI_USERNAME`, or a prompt).
- Client-credentials: `OAUTH_CLIENT_SECRET` from env, else a hidden prompt.

Login builds a client from the environment config + the supplied secret, forces
a token fetch, and writes `tokens/<env>.json`.

### Token persistence mechanics
The `GundiClient` exposes settable `cached_token`, `cached_token_expires_at`, and
`cached_token_refresh_expires_at` attributes. The token store:
- **Restore:** parse `tokens/<env>.json` into an `OAuthToken` and set those three
  attributes on a freshly built client (absolute timestamps restored as-is, so
  no recomputation and no premature refresh).
- **Persist:** after a command runs, if the client now holds a token that differs
  from what was loaded (new or refresh-rotated), write it back with recomputed
  absolute timestamps.

## Environment resolution (precedence)

For every command, the active environment is resolved in this order:
1. `--profile <name>` flag (per-command override)
2. `GUNDI_PROFILE` environment variable
3. the stored `active` environment in `config.json`
4. **raw `OAUTH_*` / `GUNDI_*` env vars** — today's behavior, used only when no
   profile is configured/selected (backward compatible).

An unknown environment name (flag or `GUNDI_PROFILE`) is an error (exit 2).

## How a normal command authenticates

1. Resolve the environment (precedence above).
2. If a profile is selected, build the client from its config; otherwise use the
   raw-env path.
3. Load `tokens/<env>.json` if present and restore it onto the client.
4. Run the command. The client uses the cached access token, refreshing via the
   refresh-token grant when needed and possible.
5. If the token was created or rotated during the run, write it back.
6. **No usable token and not refreshable:** if the needed secret is present in
   the environment, authenticate implicitly and cache the result (friendly
   fallback). Otherwise exit 1 with *run `gundi auth login`*.

## Commands

```
gundi env add <name> --base-url URL --client-id ID
                     (--issuer URL | --token-url URL)
                     [--audience AUD] [--username USER] [--scope SCOPE]
gundi env list                  # lists environments, marks the active one
gundi env show [<name>]         # prints one environment's config (no secrets)
gundi env use <name>            # set the active environment
gundi env remove <name>         # delete the environment and its cached token

gundi auth login   [--profile <name>]   # obtain + cache a token (secret via env or hidden prompt)
gundi auth logout  [--profile <name>]   # delete the cached token
gundi auth status  [--profile <name>]   # report whether a valid cached token exists, with expiry

# existing commands now resolve the environment + reuse the cached token
gundi integrations list [--type SLUG] [--json]
gundi integrations enable  <integration-id>
gundi integrations disable <integration-id>
```

`--profile` is a global option available to the `integrations` and `auth`
commands.

## Module structure

| File | Purpose |
|------|---------|
| `cli/config_store.py` | Resolve the config path (XDG), read/write `config.json`, environment CRUD, active selection, directory/file permissions. |
| `cli/token_store.py` | Serialize/restore/delete a cached token; apply a stored token onto a `GundiClient` and extract the (possibly rotated) token after a run. |
| `cli/env.py` | `gundi env` commands. |
| `cli/auth.py` | `gundi auth` commands (login/logout/status). |
| `cli/_client.py` | Refactor: `resolve_environment()` (precedence), `build_client()` (from a profile or raw env), and a run-wrapper that loads/saves the token around `run_with_client()`. Raw-env path preserved. |
| `cli/main.py` | Register `env`, `auth`, and `integrations` sub-apps. |

Each module is independently testable: `config_store`/`token_store` are pure
filesystem/serialization units with no Typer or network coupling; `env`/`auth`
are thin command layers over them.

## Error handling & exit codes

Unchanged conventions, extended:

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | API/auth error, or not-authenticated-and-not-refreshable (with a "run `gundi auth login`" hint) |
| 2 | Missing/invalid configuration: unknown environment, incomplete `env add`, or missing required auth config |

Corrupt `config.json` / token files are reported as a clear error (exit 2 for
config, exit 1 for a token cache miss that falls through to login guidance),
never a traceback.

## Testing

Isolation via `tmp_path` + monkeypatched `XDG_CONFIG_HOME` (and `HOME`); `respx`
for token/discovery endpoints.

- **config_store:** add/list/show/use/remove round-trips; active selection;
  `config.json` and dir created with `0600`/`0700`; unknown-env errors; corrupt
  file handled.
- **token_store:** serialize → restore round-trip preserves token + absolute
  expiries; restoring a still-valid token sets attributes so no refresh fires;
  `logout` deletes the file; missing file is a clean miss.
- **auth login:** builds a client from the active env, mocks the token POST
  (and discovery when issuer-based), writes `tokens/<env>.json` with `0600`;
  reads secret from env and via simulated hidden prompt.
- **auth logout/status:** logout removes the token; status reports presence and
  expiry.
- **precedence:** `--profile` > `GUNDI_PROFILE` > active > raw env, each
  exercised; raw-env path still works with no profiles configured.
- **token reuse (core guarantee):** a command run with a valid cached token
  issues **no** token POST.
- **refresh:** an expired access token with a valid refresh token triggers
  exactly one refresh-token request and persists the rotated token.
- **implicit fallback:** no cached token but secret present in env →
  authenticates and caches; secret absent → exit 1 with the login hint.
- **unknown env → exit 2.**

## Open questions

None outstanding. Grant-type refresh tradeoff (§Authentication model) and the
implicit-auth fallback (§How a normal command authenticates) are both accepted.
