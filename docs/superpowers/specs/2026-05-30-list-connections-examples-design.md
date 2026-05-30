# Design: list-connections demo examples

**Date:** 2026-05-30
**Author:** Chris Doehring (with Claude)
**Status:** Approved — pending spec review

## Context

The `gundi-client-v2` package now supports three OAuth2 auth paths:

1. **`client_credentials`** (confidential client; M2M / service-to-service)
2. **`password` grant** (public client; user-facing developer auth)
3. **OIDC discovery** — either grant, but the token endpoint is discovered
   from `OAUTH_ISSUER` instead of being passed explicitly. Lands in
   `gundi-client-v2 >= 2.6.0` (PR #41).

There is one runnable example in the repo today (`examples/send_observations.py`)
demonstrating password grant + observation posting. There is no minimal demo
of the most basic read operation — listing connections — and no demo of the
two newer auth modes (client_credentials, OIDC discovery).

This spec adds three small, self-contained example scripts that each list
the connections accessible to the configured client, differing only in the
auth path they exercise. The goal is teaching the auth modes against a
realistic call; the variation is the configuration, not the task.

## Goals

1. Three runnable example scripts in `examples/`, one per auth path, each
   listing Gundi connections via `GundiClient.get_connections(...)`.
2. Each script is **self-contained** (copy-pasteable) — no shared utility
   module. Duplication of the ~3-line print loop is preferred over coupling.
3. Each script demonstrates passing `params={...}` to `get_connections`
   for server-side filtering. The filter is generic (e.g.
   `{"status": "healthy"}`) with a comment noting "see the Gundi API for
   available filters."
4. Honest, up-front validation of required env vars: each script raises
   `ValueError` listing exactly which env vars are missing before any
   network call.

## Non-goals

- Tests for the examples (they need live credentials). Smoke-test only that
  each file parses with `ast`, matching the pattern already used for
  `send_observations.py`.
- A `--mode` flag / combined CLI. Per-file is simpler for examples.
- A shared `_print_connections()` helper module. Self-contained > DRY for
  examples.
- Reading from real PADAS infrastructure URLs.
  `.env.example` already uses `*.example.com` placeholders.
- Tutorial-style notebook-grade comment density. One concise module
  docstring per file; no inline narration.

## Files

```
examples/
  list_connections_client_credentials.py   (new)
  list_connections_password_grant.py       (new)
  list_connections_discovery.py            (new)
  .env.example                             (update — annotate per-example var usage)
  README.md                                (update — "Other examples" section)
```

All five changes land on `cd/v2-oidc-discovery` (PR #41 branch), but
**uncommitted initially** so the user can run each example against a live
Gundi before the work is committed.

## Per-script shape (~60-80 lines each)

Each script follows the same skeleton; only the env validation and the
`GundiClient(**kwargs)` call site differ. Skeleton:

```python
"""
Example: list Gundi connections using <auth-path>.

# Required env vars:
#   <auth-mode-specific list>
# Conditional:
#   OAUTH_AUDIENCE  — required by some IdPs (e.g. Auth0 won't issue a usable
#                     API access token without it); ignored by Keycloak.

Run from the examples/ directory (so the local .env is loaded):

    cd examples
    python list_connections_<mode>.py
"""

import asyncio
import os

from gundi_client_v2 import GundiClient


def _get_kwargs() -> dict:
    """Validate required env vars; raise ValueError listing any that are missing."""
    missing = []
    kwargs = {}

    base_url = os.environ.get("GUNDI_API_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    else:
        missing.append("GUNDI_API_BASE_URL")

    client_id = os.environ.get("OAUTH_CLIENT_ID")
    if client_id:
        kwargs["oauth_client_id"] = client_id
    else:
        missing.append("OAUTH_CLIENT_ID")

    # <auth-mode-specific env-var checks>
    # <e.g. OAUTH_CLIENT_SECRET for client_credentials;
    #       GUNDI_USERNAME/GUNDI_PASSWORD for password;
    #       OAUTH_ISSUER for discovery>

    if os.environ.get("OAUTH_AUDIENCE"):
        kwargs["oauth_audience"] = os.environ["OAUTH_AUDIENCE"]

    if missing:
        raise ValueError(f"Missing required env vars: {', '.join(missing)}")
    return kwargs


async def main():
    async with GundiClient(**_get_kwargs()) as client:
        # `params` is forwarded to the underlying GET request — use it to filter
        # server-side. See the Gundi API for available filters; "status" is a
        # common one (values like "healthy", "unhealthy").
        connections = await client.get_connections(params={"status": "healthy"})
        print(f"Found {len(connections)} connection(s):")
        for c in connections:
            provider = c.provider.name if c.provider else "(no provider)"
            destinations = ", ".join(d.name for d in (c.destinations or [])) or "(no destinations)"
            print(f"  {c.id}  {provider} -> {destinations}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Per-file specifics

### `list_connections_client_credentials.py`

- **Required env**: `GUNDI_API_BASE_URL`, `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_TOKEN_URL`.
- **Conditional**: `OAUTH_AUDIENCE`.
- **GundiClient kwargs**: `base_url`, `oauth_client_id`, `oauth_client_secret`, `oauth_token_url`, plus `oauth_audience` when set.
- **Wire-level grant**: `client_credentials`.
- **Docstring** notes this is the confidential-client / M2M auth path.

### `list_connections_password_grant.py`

- **Required env**: `GUNDI_API_BASE_URL`, `OAUTH_CLIENT_ID`, `GUNDI_USERNAME`, `GUNDI_PASSWORD`, `OAUTH_TOKEN_URL`.
- **Conditional**: `OAUTH_AUDIENCE`.
- **GundiClient kwargs**: `base_url`, `oauth_client_id`, `username`, `password`, `oauth_token_url`, plus `oauth_audience` when set. **No** `oauth_client_secret`.
- **Wire-level grant**: `password`.
- **Docstring** notes this is the user-facing developer auth path; public OAuth client.

### `list_connections_discovery.py`

- **Required env**: `GUNDI_API_BASE_URL`, `OAUTH_CLIENT_ID`, `OAUTH_ISSUER`, `GUNDI_USERNAME`, `GUNDI_PASSWORD`.
- **Conditional**: `OAUTH_AUDIENCE`.
- **GundiClient kwargs**: `base_url`, `oauth_client_id`, `username`, `password`, `oauth_issuer` (NOT `oauth_token_url`), plus `oauth_audience` when set.
- **Wire-level grant**: `password`; the token endpoint is discovered at
  `{OAUTH_ISSUER}/.well-known/openid-configuration` and cached for the
  process lifetime.
- **Docstring** notes:
  - Requires `gundi-client-v2 >= 2.6.0` (the OIDC discovery release).
  - This is the path that will work post-Auth0 migration with no code change.
  - The first auth incurs one extra HTTP request (the discovery doc); cached thereafter.

## `.env.example` update

Keep `.env.example` as the union of all vars used across the four examples
(the three new ones + `send_observations.py`). Annotate each var with which
example(s) require it. The file already uses `*.example.com` placeholders
and already marks the API base URLs as required — no change needed there.

Resulting comment structure:

```
# Required for all examples:
GUNDI_API_BASE_URL=https://api.example.com
OAUTH_CLIENT_ID=your-oauth-client-id

# Required by list_connections_client_credentials.py:
OAUTH_CLIENT_SECRET=your-oauth-client-secret

# Required by list_connections_password_grant.py and send_observations.py:
GUNDI_USERNAME=your-username
GUNDI_PASSWORD=your-password
GUNDI_INTEGRATION_NAME="Your Integration Name"  # send_observations.py only

# Token URL — required by client_credentials / password_grant examples
# (when not using OIDC discovery):
OAUTH_TOKEN_URL=https://auth.example.com/realms/your-realm/protocol/openid-connect/token

# Required by list_connections_discovery.py (alternative to OAUTH_TOKEN_URL):
OAUTH_ISSUER=https://auth.example.com/realms/your-realm

# Conditional: required by some IdPs (e.g., Auth0); optional for Keycloak.
OAUTH_AUDIENCE=your-oauth-audience

# Sensors/routing API base URL — required by send_observations.py:
SENSORS_API_BASE_URL=https://sensors.api.example.com

# Optional
# GUNDI_API_SSL_VERIFY=true
# LOG_LEVEL=INFO
```

## `examples/README.md` update

Add a short "Other examples" section (under the existing `send_observations.py`
documentation) with a small table:

| Script | Auth path | Token URL source |
|---|---|---|
| `list_connections_client_credentials.py` | client_credentials grant | explicit `OAUTH_TOKEN_URL` |
| `list_connections_password_grant.py` | password grant | explicit `OAUTH_TOKEN_URL` |
| `list_connections_discovery.py` | password grant | OIDC discovery from `OAUTH_ISSUER` (requires v2.6.0) |

Plus a one-line "all three run the same way: `cd examples && python list_connections_<mode>.py`."

## Smoke-verify (no commit until user has tested)

After writing the files:

```
./.venv/bin/python -c "import ast; [ast.parse(open(f).read()) for f in [
    'examples/list_connections_client_credentials.py',
    'examples/list_connections_password_grant.py',
    'examples/list_connections_discovery.py',
]]; print('all parse')"
./.venv/bin/python -m pytest -q
```

Expected: all three parse; test suite stays green (no test files changed —
suite count unchanged from the current PR #41 branch state).

Files are then left **uncommitted** on `cd/v2-oidc-discovery` for the user
to test against a live Gundi (and/or staging). After the user reports
results / approves, a single commit lands the five-file delta on the
branch:

```
ci: list-connections demo examples for the three auth paths
```

## Out-of-scope / known limitations

- `params={"status": "healthy"}` is a guess at a sensible filter. If the
  real Gundi API doesn't accept this exact key, the example needs adjustment
  during live testing. The point is to demonstrate the params mechanism;
  the specific filter is illustrative.
- The discovery example will fail at runtime if the user's installed
  `gundi-client-v2 < 2.6.0` (it relies on the `oauth_issuer` kwarg + OIDC
  discovery logic that doesn't exist before PR #41 lands). Docstring makes
  this version requirement explicit.
- Reading from a `.env` file relies on the existing `env.read_env()` in
  `settings.py` — running from `examples/` cwd picks up `examples/.env`, or
  set `GUNDI_CLIENT_ENVFILE=path/to/.env` from elsewhere.

## Versioning impact

None. These are example files only; no library code or version change.
