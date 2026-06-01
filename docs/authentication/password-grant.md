# Password grant

The `password` grant (Resource Owner Password Credentials, ROPC; RFC 6749
§4.3) authenticates a user by sending their username and password directly
to the IdP.

!!! warning "ROPC is discouraged by OAuth 2.1"
    OAuth 2.1 (RFC 9700) discourages ROPC in favor of authorization-code
    flows with PKCE. `gundi-client-v2` supports it for legacy and CLI use
    cases where redirect-based flows aren't practical, and for public
    clients that don't have a secret.

## When to use it

- Your code runs in a context where you have the user's credentials
  (a CLI tool, a desktop utility, an internal admin script).
- Your OAuth client is **public** (no client secret).
- You need to act *as the user*, not as a system account.

## Environment variables

```env
GUNDI_API_BASE_URL=https://api.gundiservice.org
OAUTH_ISSUER=https://auth.gundiservice.org/realms/your-realm
OAUTH_CLIENT_ID=your-client-id
GUNDI_USERNAME=your-username
GUNDI_PASSWORD=your-password
# OAUTH_AUDIENCE=your-api-audience   # required by some IdPs (e.g. Auth0)
```

## Minimal example

```python
import asyncio
from gundi_client_v2 import GundiClient


async def main():
    async with GundiClient() as client:
        integrations = []
        async for integration in client.get_integrations():
            integrations.append(integration)
        print(f"User has access to {len(integrations)} integrations")


asyncio.run(main())
```

## What's on the wire

```
grant_type=password
client_id=<OAUTH_CLIENT_ID>
username=<GUNDI_USERNAME>
password=<GUNDI_PASSWORD>
scope=openid
audience=<OAUTH_AUDIENCE>     # only if set
```

No `client_secret` — public clients don't have one.

## Refresh behavior

A successful password-grant response typically includes a `refresh_token`.
The library caches it and uses it on the next expiry (RFC 6749 §6) to avoid
re-sending the user's credentials.

If the server rotates the refresh token on each refresh (default in
Keycloak), the new one replaces the cached one. If the server omits a new
refresh token in the refresh response (also allowed by §6), the library
reuses the existing cached refresh token until it too expires.

When the refresh token itself expires, the library falls back to a fresh
password grant — provided `GUNDI_USERNAME` and `GUNDI_PASSWORD` are still
in the env. If they've been unset, you'll see an `AuthenticationError`.

## Constructing the client explicitly

```python
client = GundiClient(
    base_url="https://api.gundiservice.org",
    oauth_issuer="https://auth.gundiservice.org/realms/your-realm",
    oauth_client_id="your-client-id",
    username="your-username",
    password="your-password",
)
```

## See also

- [Client credentials](client-credentials.md) for confidential M2M clients
- [OIDC discovery](oidc-discovery.md) for issuer-based token endpoint resolution
- [Refresh and errors](refresh-and-errors.md) for refresh-rotation details
