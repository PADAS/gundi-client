# Authentication overview

`gundi-client-v2` supports three OAuth2 authentication paths. All three end
the same way — the client holds an access token and attaches it to every
outgoing request — but they differ in how that token is obtained.

## The three paths

| Path | Grant | When | Client type |
|---|---|---|---|
| [Client credentials](client-credentials.md) | `grant_type=client_credentials` (RFC 6749 §4.4) | Server-to-server, no user identity | **Confidential** (has a secret) |
| [Password grant](password-grant.md) | `grant_type=password` (ROPC; RFC 6749 §4.3) | Acting on behalf of a specific user | **Public** (no secret) |
| [OIDC discovery](oidc-discovery.md) | Either of the above, with token endpoint discovered automatically | Any IdP that supports OIDC Discovery 1.0 | Either |

OIDC discovery is **not a separate grant type** — it's a mechanism for the
library to discover the IdP's token endpoint at runtime from
`{GUNDI_OAUTH_ISSUER}/.well-known/openid-configuration`. You combine it with one of
the other two grants.

The un-prefixed `OAUTH_*` names (and, for the library, the legacy `KEYCLOAK_*`
names) are still accepted as fallbacks.

## How the client picks a grant

When you call any method on `GundiClient` that requires authentication, it
chooses a grant in this priority order:

1. If a **non-expired refresh token** is cached → refresh-token grant
   (RFC 6749 §6).
2. If `username` + `password` were provided → password grant.
3. If `client_secret` was provided → client_credentials grant.
4. Otherwise → `AuthenticationError`.

You don't normally call the grant functions directly; the client handles it.
But the standalone functions in `gundi_client_v2.auth` are available if you
need fine-grained control:

```python
from gundi_client_v2.auth import (
    get_access_token_client_credentials,
    get_access_token_password_grant,
    refresh_access_token,
    discover_token_endpoint,
)
```

## Resolving the token endpoint

The library needs to know **where** to POST the token request. Two ways to
configure this, in priority order:

1. **`GUNDI_OAUTH_TOKEN_URL`** (or the `oauth_token_url` kwarg) — set this
   directly to a fully-qualified URL like
   `https://auth.example.com/realms/myrealm/protocol/openid-connect/token`.
2. **`GUNDI_OAUTH_ISSUER`** (or the `oauth_issuer` kwarg) — set this to the
   issuer base URL; the library performs OIDC discovery to resolve the token
   endpoint. The result is cached for the process lifetime; call
   `auth.clear_discovery_cache()` to invalidate.

If neither is set, the client raises `AuthenticationError`.

## Errors you might see

| Error | Likely cause |
|---|---|
| `AuthenticationError: Token request failed: HTTP 401 (invalid_client)` | Wrong client ID or secret |
| `AuthenticationError: Token request failed: HTTP 401 (invalid_grant)` | Wrong username/password, or a revoked refresh token |
| `AuthenticationError: OIDC discovery failed for ...` | Issuer URL unreachable or doesn't expose `.well-known/openid-configuration` |
| `AuthenticationError: ...returned issuer ... does not match the expected issuer` | The discovery doc's `issuer` claim doesn't match the URL you used to fetch it — possible misconfiguration or man-in-the-middle |

Full details on each, with mitigation steps:
[Refresh and errors](refresh-and-errors.md).

## See also

- [Client credentials](client-credentials.md) — confidential clients, M2M flows
- [Password grant](password-grant.md) — user-facing flows
- [OIDC discovery](oidc-discovery.md) — IdP-agnostic token endpoint resolution
- [Refresh and errors](refresh-and-errors.md) — refresh token rotation, error scenarios
