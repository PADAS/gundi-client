# OIDC discovery

OIDC Discovery 1.0 specifies that any OIDC-compliant IdP MUST expose a
metadata document at `{issuer}/.well-known/openid-configuration`. That
document includes the `token_endpoint`, `authorization_endpoint`, supported
scopes, and other configuration.

`gundi-client-v2` uses this to **avoid hard-coding** the token endpoint URL.
Set `GUNDI_OAUTH_ISSUER` to the IdP's issuer base URL, and the library fetches and
caches the resolved token endpoint at runtime.

## When to use it

- You don't want to look up and hard-code the exact token endpoint URL.
- You're rolling the same code out against multiple IdPs (Keycloak,
  Auth0, Okta, Azure AD).
- You want to be resilient to the IdP team changing the token endpoint
  path (rare, but possible).

## Environment variable

```env
GUNDI_OAUTH_ISSUER=https://auth.gundiservice.org/realms/your-realm
```

Combine with the credentials for your chosen grant
([client_credentials](client-credentials.md) or
[password](password-grant.md)).

## What happens at runtime

1. The first authentication attempt calls
   `auth.discover_token_endpoint(session, issuer)`.
2. The function GETs `{issuer.rstrip('/')}/.well-known/openid-configuration`.
3. It validates that the document's `issuer` claim matches the URL used to
   fetch it (OIDC Discovery 1.0 §4.3 — protects against
   misconfiguration and man-in-the-middle).
4. The resolved `token_endpoint` is cached in a module-level dict keyed by
   the normalized issuer.
5. Subsequent authentication attempts reuse the cached value.

The cache lives for the process lifetime. Long-running services that need
to pick up an IdP configuration change without restarting can call:

```python
from gundi_client_v2.auth import clear_discovery_cache

clear_discovery_cache()
```

## Performance note

OIDC discovery adds **one** extra HTTP request to the very first
authentication. Subsequent requests in the same process do no additional
network I/O for discovery.

## Skipping discovery

If your IdP doesn't expose a discovery document, or you want to skip the
extra request, set `GUNDI_OAUTH_TOKEN_URL` directly instead. When both are set,
`GUNDI_OAUTH_TOKEN_URL` wins:

```env
GUNDI_OAUTH_TOKEN_URL=https://auth.example.com/realms/myrealm/protocol/openid-connect/token
```

## Errors

| Error | Meaning |
|---|---|
| `OIDC discovery failed for ...` | Network error or non-2xx response fetching the discovery document. Check connectivity and that the issuer URL is correct. |
| `OIDC discovery document at ... is not valid JSON` | The discovery endpoint returned something that isn't JSON. Check that the URL is correct and not returning an HTML error page. |
| `OIDC discovery document at ... is not a JSON object` | The endpoint returned JSON, but not an object. Almost certainly an IdP bug. |
| `OIDC discovery document at ... returned issuer ... which does not match the expected issuer ...` | The `issuer` claim in the discovery doc doesn't match the URL used to fetch it. Common cause: trailing slash mismatch (the library normalizes both via `rstrip('/')`, so this shouldn't trip you up), or IdP misconfiguration. |
| `OIDC discovery document at ... is missing 'token_endpoint'` | The IdP exposed a discovery document but didn't include the required `token_endpoint` field. Almost certainly an IdP bug. |

## See also

- [Refresh and errors](refresh-and-errors.md) for general auth-error handling
- The full example: [`examples/list_connections_discovery.py`](https://github.com/PADAS/gundi-client/blob/v2/examples/list_connections_discovery.py)
