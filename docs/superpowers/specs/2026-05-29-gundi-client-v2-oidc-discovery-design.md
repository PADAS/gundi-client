# Design: OIDC discovery + drop uma-ticket grant

**Date:** 2026-05-29
**Author:** Chris Doehring (with Claude)
**Status:** Approved — pending spec review

## Context

The `gundi-client-v2` package currently derives its OAuth token URL with a
Keycloak-specific path:

```python
OAUTH_TOKEN_URL = f"{OAUTH_ISSUER}/protocol/openid-connect/token" if OAUTH_ISSUER else None
```

The rename to `OAUTH_*` config naming (PR #35) implied OAuth2-generic behavior,
but this derivation only works for Keycloak. Gundi is being migrated to Auth0,
whose token endpoint sits at `https://{tenant}.auth0.com/oauth/token` — a
different path shape — so the derivation would silently break that migration.

Separately, the confidential-client grant uses the Keycloak-specific
`urn:ietf:params:oauth:grant-type:uma-ticket`. This was a mistake; the standard
confidential-client grant is `client_credentials`, which is what Auth0 and every
other OAuth2-compliant IdP expect.

This spec covers both concerns in one PR, because they touch the same auth
code path and the Auth0 migration depends on both.

## Goals

1. Replace the Keycloak-shaped token URL derivation with **OIDC discovery**
   (`{issuer}/.well-known/openid-configuration`), so the library works against
   any OIDC-compliant IdP (Keycloak, Auth0, Okta, …) with no IdP-specific paths.
2. Drop the `uma-ticket` grant and replace the confidential-client path with
   standard `client_credentials`.
3. Honor caching that is **dead simple** — module-level dict keyed by issuer,
   process-lifetime, no TTL.

## Non-goals

- Implementing the Auth0 migration itself (different audience, scope, etc.) —
  that is a deployment-side change and a separate concern.
- OIDC client authentication methods beyond what we already support (basic
  vs. POST body) — out of scope.
- Token introspection, userinfo, JWKS validation — not needed for our use case.

## Public surface changes

**Added:**
- `oauth_issuer` kwarg on `GundiClient` (settings already exposes
  `OAUTH_ISSUER`; just surfacing it as a constructor kwarg).

**Behavior changes:**
- `OAUTH_TOKEN_URL` becomes a **direct env var** (read by `env.str(...)`); no
  longer derived at settings-load time.
- The confidential-client branch in `_refresh_token` now sends
  `grant_type=client_credentials` instead of the Keycloak uma-ticket grant.

**Removed:**
- The settings-layer derivation
  `OAUTH_TOKEN_URL = f"{OAUTH_ISSUER}/protocol/openid-connect/token"`.
- The `UMA_TICKET_GRANT_TYPE` constant in `auth.py`.
- `auth.get_access_token` (uma-ticket flavor); replaced by
  `auth.get_access_token_client_credentials`.

**Unchanged:**
- `password` grant flow + `refresh_token` grant flow (and all the OAuth2
  hardening from PR #38).
- All other kwargs (`username`, `password`, `oauth_scope`, `oauth_audience`,
  `use_ssl`, timeouts, retries).
- `keycloak_*` legacy kwarg aliases (`keycloak_client_id`,
  `keycloak_client_secret`, `keycloak_audience`).
- `KEYCLOAK_*` env-var fallbacks in `settings.py`.
- Module-level `KEYCLOAK_*` aliases of the `OAUTH_*` settings.
- Credential precedence (password grant wins over client_credentials).

## Token URL resolution

A new helper on `GundiClient`:

```python
async def _resolve_token_url(self) -> str:
    if self.oauth_token_url:
        return self.oauth_token_url
    if self.oauth_issuer:
        return await auth.discover_token_endpoint(self._session, self.oauth_issuer)
    raise errors.AuthenticationError(
        "No token URL configured. Set oauth_token_url or oauth_issuer."
    )
```

Resolution order (explicit > discovered > error):
1. `self.oauth_token_url` set → use it as-is.
2. Else `self.oauth_issuer` set → call `auth.discover_token_endpoint(...)`.
3. Else raise `AuthenticationError`.

Called once at the top of `_refresh_token`; the resolved URL is passed to each
`auth.get_access_token_*` function.

## Discovery function

Lives in `auth.py`:

```python
_DISCOVERY_CACHE: dict[str, str] = {}


def clear_discovery_cache() -> None:
    """Clear the OIDC discovery cache. Useful for tests and for long-running
    processes that need to pick up an IdP configuration change without a restart."""
    _DISCOVERY_CACHE.clear()


async def discover_token_endpoint(session, issuer: str) -> str:
    """Fetch the OIDC discovery document at {issuer}/.well-known/openid-configuration
    and return its token_endpoint. Cached per-issuer for the process lifetime;
    call clear_discovery_cache() to invalidate."""
    # Normalize so issuer values that differ only by a trailing slash share a cache entry.
    key = issuer.rstrip("/")
    if key in _DISCOVERY_CACHE:
        return _DISCOVERY_CACHE[key]
    discovery_url = f"{key}/.well-known/openid-configuration"
    try:
        response = await session.get(discovery_url)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise AuthenticationError(
            f"OIDC discovery failed for {issuer}: {e}"
        ) from e
    try:
        token_endpoint = response.json()["token_endpoint"]
    except (ValueError, KeyError, TypeError) as e:
        raise AuthenticationError(
            f"OIDC discovery document at {discovery_url} is missing 'token_endpoint'"
        ) from e
    _DISCOVERY_CACHE[key] = token_endpoint
    return token_endpoint
```

Notes:
- The cache key is `issuer.rstrip("/")`, so `https://x/` and `https://x` share a
  cache entry and never cause two discovery roundtrips for the same logical IdP.
- `clear_discovery_cache()` is the public escape hatch — used by the autouse
  test fixture (below) and available to long-running processes that need to
  pick up an IdP configuration change without restarting.
- Failure mode is **strict**: any discovery error raises
  `AuthenticationError`. No silent fallback to a hardcoded path; debugging a
  bad issuer config is clearer when it fails loudly.
- Caching is process-lifetime, no TTL. The realistic risk (an IdP changing its
  `token_endpoint` mid-process) is rare enough that TTL's failure modes (a
  routine cache-miss roundtrip that can fail on a transient IdP outage and
  surface as an auth failure) aren't worth the trade.

## `client_credentials` replacement

```python
async def get_access_token_client_credentials(
    session, oauth_token_url, client_id, client_secret, audience=None, scope="openid"
):
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
    }
    if audience:
        payload["audience"] = audience
    body = await _post_token(session, oauth_token_url, payload)
    # RFC 6749 §4.4.3: client_credentials responses SHOULD NOT include a
    # refresh_token. Backfill empty values so OAuthToken.parse_obj succeeds,
    # and the client_credentials path always re-authenticates on access-token
    # expiry rather than attempting refresh.
    body.setdefault("refresh_token", "")
    body.setdefault("refresh_expires_in", 0)
    return OAuthToken.parse_obj(body)
```

The empty `refresh_token` plus `refresh_expires_in=0` signal "no usable
refresh token" to `_store_token`, which sets `cached_token_refresh_expires_at`
accordingly so the refresh-grant branch in `_refresh_token` is naturally
skipped.

## `_store_token` adjustment

```python
def _store_token(self, token, *, refresh_rotated=True):
    now = datetime.now(tz=timezone.utc)
    self.cached_token = token
    self.cached_token_expires_at = now + timedelta(
        seconds=self._expiry_with_buffer(token.expires_in)
    )
    if refresh_rotated and token.refresh_token and token.refresh_expires_in > 0:
        self.cached_token_refresh_expires_at = now + timedelta(
            seconds=self._expiry_with_buffer(token.refresh_expires_in)
        )
    elif refresh_rotated:
        # Token came from a grant that doesn't issue refresh tokens
        # (e.g., client_credentials). Disable refresh tracking.
        self.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)
    # else (refresh_rotated=False): preserve the existing cached_token_refresh_expires_at,
    # per the partial-refresh handling from PR #38.
```

## `_refresh_token` updated branches

Roughly:

```python
async def _refresh_token(self):
    now = datetime.now(tz=timezone.utc)
    token_url = await self._resolve_token_url()

    # 1. Refresh-token grant (unchanged, takes resolved url)
    if (
        self.cached_token
        and self.cached_token.refresh_token
        and self.cached_token_refresh_expires_at > now
    ):
        try:
            token, refresh_rotated = await auth.refresh_access_token(
                session=self._session,
                oauth_token_url=token_url,
                ...
            )
            self._store_token(token, refresh_rotated=refresh_rotated)
            return token
        except errors.AuthenticationError:
            logger.info("Refresh-token grant failed; falling back to full re-authentication.")
            self.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)

    # 2. Password grant (unchanged, takes resolved url)
    if self.username and self.password and self.client_id:
        token = await auth.get_access_token_password_grant(
            session=self._session,
            oauth_token_url=token_url,
            client_id=self.client_id,
            username=self.username,
            password=self.password,
            audience=self.audience,
            scope=self.scope,
        )
    # 3. Client-credentials grant (REPLACES uma-ticket)
    elif self.client_id and self.client_secret:
        token = await auth.get_access_token_client_credentials(
            session=self._session,
            oauth_token_url=token_url,
            client_id=self.client_id,
            client_secret=self.client_secret,
            audience=self.audience,
            scope=self.scope,
        )
    else:
        raise errors.AuthenticationError(
            "No credentials configured. Provide a client_id with either "
            "username/password (public client) or client_secret (confidential client)."
        )
    self._store_token(token)
    return token
```

## Settings changes (`settings.py`)

```python
OAUTH_ISSUER = env.str("OAUTH_ISSUER", env.str("KEYCLOAK_ISSUER", None))
OAUTH_TOKEN_URL = env.str("OAUTH_TOKEN_URL", None)   # now read directly from env
OAUTH_CLIENT_ID = env.str("OAUTH_CLIENT_ID", env.str("KEYCLOAK_CLIENT_ID", None))
OAUTH_CLIENT_SECRET = env.str("OAUTH_CLIENT_SECRET", env.str("KEYCLOAK_CLIENT_SECRET", None))
OAUTH_AUDIENCE = env.str("OAUTH_AUDIENCE", env.str("KEYCLOAK_AUDIENCE", None))
OAUTH_SCOPE = env.str("OAUTH_SCOPE", "openid")

# Backward-compat module-level aliases for KEYCLOAK_*
KEYCLOAK_ISSUER = OAUTH_ISSUER
KEYCLOAK_CLIENT_ID = OAUTH_CLIENT_ID
KEYCLOAK_CLIENT_SECRET = OAUTH_CLIENT_SECRET
KEYCLOAK_AUDIENCE = OAUTH_AUDIENCE
```

The derived `f"{OAUTH_ISSUER}/protocol/..."` line is removed.

## Test plan

All tests use `respx` mocks. A new autouse `conftest.py` fixture calls
`auth.clear_discovery_cache()` between tests so cache state doesn't leak.

**Discovery:**
- success → returns `token_endpoint` from the mocked discovery doc
- cached on second call → no second HTTP request fires
- discovery 5xx → `AuthenticationError("OIDC discovery failed …")`
- discovery 200 with missing `token_endpoint` → `AuthenticationError("… missing 'token_endpoint'")`
- trailing slash on issuer does not produce a double-slash in discovery URL
- `https://x` and `https://x/` share a cache entry (only one discovery roundtrip)
- `clear_discovery_cache()` invalidates so the next call re-fetches

**`GundiClient` token URL resolution:**
- explicit `oauth_token_url` → no discovery roundtrip
- only `oauth_issuer` → discovery fires, then token request
- neither set → `AuthenticationError("No token URL configured…")`

**`client_credentials` grant:**
- payload: `grant_type=client_credentials`, includes `client_secret`,
  conditional `audience`, configurable `scope`
- response without `refresh_token` parses cleanly and disables refresh tracking
  (`cached_token_refresh_expires_at == datetime.min`)
- on access-token expiry, next call goes back through full client_credentials
  auth (not the refresh path)

**Existing tests:**
- `gundi_client_v2` conftest fixture sets `oauth_token_url` directly, so
  discovery never fires for the unrelated suites
- the confidential-mode tests' token-request body changes grant_type from
  uma-ticket to client_credentials; existing assertions don't check
  grant_type, so they continue to pass
- `test_confidential_refresh_sends_client_secret`: still valid; the mocked
  initial response includes `refresh_token`, so the refresh path activates
  on `force_refresh_token=True`

## Migration & backward compatibility

- **Existing deployments** currently using `OAUTH_ISSUER` (Keycloak) for URL
  derivation now go through OIDC discovery instead. Keycloak supports
  discovery natively; the resulting `token_endpoint` is the same URL the old
  derivation produced. No deployment-side change required.
- **`OAUTH_TOKEN_URL`** explicitly in env now actually works (it didn't
  before — this closes the docs/code gap Copilot flagged on #39).
- **Auth0 cut-over** later: set `OAUTH_ISSUER` to the Auth0 tenant URL (and
  adjust `OAUTH_AUDIENCE`/`OAUTH_SCOPE` per Auth0). No code change needed.
- **`keycloak_*` legacy support** stays in place — kwargs, env vars, module
  aliases.

## Versioning

The change set adds a public-surface kwarg (`oauth_issuer`), removes an
internal function (`auth.get_access_token`), and changes the wire grant_type
for confidential clients. Treating as a minor version bump:
`__version__ = "2.5.0"` → `"2.6.0"`.

## File inventory

- Modify: `gundi_client_v2/settings.py`
- Modify: `gundi_client_v2/auth.py` (drop uma-ticket; add discovery + client_credentials)
- Modify: `gundi_client_v2/client.py` (`__init__` adds `oauth_issuer`; `_refresh_token` uses `_resolve_token_url`; `_store_token` handles refreshless tokens)
- Modify: `gundi_client_v2/__init__.py` (version bump)
- Modify: `tests/conftest.py` (autouse fixture clearing `_DISCOVERY_CACHE`)
- New tests: `tests/client/test_oidc_discovery.py` (discovery happy path / cache / failure / trailing slash / token URL resolution)
- Modify tests: `tests/client/test_password_grant.py` (rename remaining uma-ticket assertions; add client_credentials payload tests; add no-refresh-token client_credentials test)
- Modify: `README.md` (replace the "Keycloak-derived" note with OIDC discovery explanation; update env-var table)
