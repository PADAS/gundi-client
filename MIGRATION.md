# Migration guide

## 3.7.0 — `GUNDI_OAUTH_*` env var names

The preferred env var names for OAuth configuration are now prefixed with
`GUNDI_` to avoid collisions with other tools sharing an environment:

| Old (still accepted) | New (preferred) |
|---|---|
| `OAUTH_ISSUER` | `GUNDI_OAUTH_ISSUER` |
| `OAUTH_TOKEN_URL` | `GUNDI_OAUTH_TOKEN_URL` |
| `OAUTH_CLIENT_ID` | `GUNDI_OAUTH_CLIENT_ID` |
| `OAUTH_CLIENT_SECRET` | `GUNDI_OAUTH_CLIENT_SECRET` |
| `OAUTH_AUDIENCE` | `GUNDI_OAUTH_AUDIENCE` |
| `OAUTH_SCOPE` | `GUNDI_OAUTH_SCOPE` |

No action is required: the old `OAUTH_*` names (and the pre-3.0 `KEYCLOAK_*`
names, for the library) keep working as silent fallbacks. When both spellings
are set, the `GUNDI_`-prefixed one wins.

## Upgrading to 3.0 from 2.x

This release modernizes the OAuth2 implementation, bumps the `httpx` runtime
dependency, and adds OIDC discovery and routes CRUD. Most consumers will need
to update their lockfile and bump a small set of transitive dependencies.

### TL;DR — what every consumer needs to change

1. **Bump the pin** in `requirements-base.in` (or equivalent):
   `gundi-client-v2~=2.4.0` → `gundi-client-v2~=3.0.0`
2. **Bump fastapi and starlette together** if you use FastAPI's `TestClient`
   (most integrations do). Minimum compatible quadruple:

   | Package | Minimum | Reason |
   |---|---|---|
   | `gundi-client-v2` | `3.0.0` | this release |
   | `httpx` | `0.28` | required transitively |
   | `starlette` | `0.37` | older versions call `httpx.Client(app=...)`, which `httpx>=0.28` removed |
   | `fastapi` | `0.110.3` | first release that allows `starlette>=0.37`; still compatible with `pydantic~=1.10` |

3. **Regenerate the lockfile** (`uv pip compile -o requirements.txt ...` or the
   equivalent `pip-compile` invocation).
4. **Run your test suite.** If a `TestClient(app)` call raises
   `TypeError: Client.__init__() got an unexpected keyword argument 'app'`,
   your starlette is still pinned below 0.37 — your fastapi bump didn't go
   high enough.

A known-good combination tested against `gundi-integration-earthranger`:

```
gundi-client-v2==3.0.0
httpx==0.28.1
starlette==0.37.2
fastapi==0.110.3
pydantic==1.10.26   # still on the v1 line; v2 not required
```

### Authentication: uma-ticket grant removed

`gundi-client-v2` no longer uses the Keycloak-specific `uma-ticket` grant for
server-to-server authentication. It now uses the standard OAuth2
`client_credentials` grant (RFC 6749 §4.4).

**What this means at the call site:** nothing. The client constructor signature
is unchanged. `GundiClient()` reads the same env vars and still authenticates
transparently before each request.

**What this means at the IdP:** if your service uses a confidential client
configured for the uma-ticket flow specifically, confirm the same client can
issue tokens via `client_credentials`. For Keycloak, this is the default; no
change required unless you have explicitly disabled the grant. For Auth0, see
the audience note below.

### Settings: token URL derivation → OIDC discovery

**Old behavior (2.x):** the client constructed the token URL at import time:

```python
# 2.x — in gundi_client_v2/settings.py
KEYCLOAK_ISSUER = env.str("KEYCLOAK_ISSUER", None)
OAUTH_TOKEN_URL = f"{KEYCLOAK_ISSUER}/protocol/openid-connect/token"
```

This worked only against Keycloak-shaped paths.

**New behavior (3.0):** the client either reads `OAUTH_TOKEN_URL` directly, or
discovers it via OIDC at `{OAUTH_ISSUER}/.well-known/openid-configuration`.
The pre-existing env var names (`KEYCLOAK_ISSUER`, `KEYCLOAK_CLIENT_ID`,
`KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_AUDIENCE`) still work — they're aliased to
the corresponding `OAUTH_*` names.

**Migration paths, in order of preference:**

1. **No changes needed (recommended)** if your deployment already exports
   `KEYCLOAK_ISSUER` and your IdP serves a well-formed
   `/.well-known/openid-configuration` document (Keycloak, Auth0, Okta, Azure
   AD, etc.). The client will discover the token endpoint at runtime, validate
   the `issuer` claim per OIDC Discovery 1.0 §4.3, and cache the result for
   the process lifetime.
2. **Set `OAUTH_TOKEN_URL` directly** if your IdP doesn't expose a discovery
   document or you want to skip the one-time discovery request. This overrides
   discovery when set.

**What does NOT work anymore:** setting only `KEYCLOAK_AUTH_SERVICE` and
`KEYCLOAK_REALM` in env (without `KEYCLOAK_ISSUER` or `OAUTH_ISSUER` or
`OAUTH_TOKEN_URL`). The 2.x library did not read those two env vars either —
your existing deployment must be exporting `KEYCLOAK_ISSUER` already, or 2.x
authentication wouldn't have worked.

### OAuth audience (`OAUTH_AUDIENCE` / `KEYCLOAK_AUDIENCE`)

This parameter is IdP-dependent:

- **Auth0 password grant**: required. Without it, Auth0 issues an opaque token
  that cannot be used as an API access token.
- **Keycloak password grant**: ignored. The `aud` claim is determined by the
  client configuration in the realm.
- **Other IdPs**: consult their documentation. RFC 8707 specifies the
  `resource` parameter as the standard alternative for resource indicators;
  some IdPs accept either.

The library passes whatever you set; it does not interpret the value.

### New capabilities (opt-in)

These are available after upgrade but don't require changes to existing code:

- **OIDC discovery** via `OAUTH_ISSUER` env var or the `oauth_issuer` kwarg
  to `GundiClient(...)`. See `gundi_client_v2/auth.py::discover_token_endpoint`.
- **Routes CRUD**: `get_routes()`, `get_route_details(route_id)`,
  `get_routes_for_connection(connection_id)`, `create_route(data)`,
  `update_route(route_id, data)`, `delete_route(route_id)`.
- **Password grant** for user-facing flows (existing in 2.x, refined in 3.0).
  See `examples/list_connections_password_grant.py`.
- **Refresh token rotation** handled per RFC 6749 §6 (server may omit the
  rotated refresh token; the client reuses the cached one).

### Troubleshooting

**`TypeError: Client.__init__() got an unexpected keyword argument 'app'`**
Your starlette is below 0.37 but httpx is 0.28+. Bump fastapi to `>=0.110.3`
and re-resolve.

**`pip` resolver fails to find a satisfying set of versions**
Most often: your lockfile pins `httpcore==0.17.x` (paired with httpx 0.24). Run
a fresh resolve, don't try to install on top of the old lockfile.

**`AuthenticationError: OIDC discovery failed for ...`**
The client tried to discover the token endpoint and got a network error. Check
network reachability to your IdP and that `{OAUTH_ISSUER}/.well-known/openid-configuration`
returns a 200. As a fallback, set `OAUTH_TOKEN_URL` directly.

**`AuthenticationError: ...returned issuer ...does not match the expected issuer`**
The discovery document's `issuer` claim doesn't match the URL the client used
to fetch it. This is the OIDC Discovery 1.0 §4.3 validation. Common causes:
trailing slash differences (the client normalizes via `rstrip('/')` on both
sides, so this shouldn't trip you up), or an IdP misconfiguration.

**Authentication worked in 2.x but fails in 3.0 with no obvious error**
Check that the deployment env actually exports `KEYCLOAK_ISSUER` (or
`OAUTH_ISSUER` or `OAUTH_TOKEN_URL`). Some consumer settings modules compose
`KEYCLOAK_ISSUER` from `KEYCLOAK_AUTH_SERVICE + KEYCLOAK_REALM` as a Python
local variable, which the client cannot see.
