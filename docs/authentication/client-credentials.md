# Client credentials grant

The `client_credentials` grant (RFC 6749 §4.4) is the standard OAuth2 flow
for **server-to-server** authentication. There is no user identity involved
— your service authenticates as itself using a client ID and secret.

## When to use it

- Your service is a confidential client (the secret can be kept private).
- The actions you perform are not tied to a specific user.
- Common use: batch jobs, schedulers, integrations that act as a system
  account.

## Environment variables

```env
GUNDI_API_BASE_URL=https://api.gundiservice.org
OAUTH_ISSUER=https://auth.gundiservice.org/realms/your-realm
OAUTH_CLIENT_ID=your-client-id
OAUTH_CLIENT_SECRET=your-client-secret
# OAUTH_AUDIENCE=your-api-audience   # required by some IdPs (e.g. Auth0)
```

## Minimal example

```python
import asyncio
from gundi_client_v2 import GundiClient


async def main():
    async with GundiClient() as client:
        connections = await client.get_connections()
        print(f"{len(connections)} connections accessible to this client")


asyncio.run(main())
```

The client reads the env vars at construction time. The first request
triggers an initial `client_credentials` token request; subsequent requests
reuse the cached token until it expires.

## What's on the wire

The library POSTs to the token endpoint with:

```
grant_type=client_credentials
client_id=<OAUTH_CLIENT_ID>
client_secret=<OAUTH_CLIENT_SECRET>
scope=openid
audience=<OAUTH_AUDIENCE>     # only if set
```

The token endpoint is either `OAUTH_TOKEN_URL` directly, or resolved via
OIDC discovery from `OAUTH_ISSUER`.

## Refresh behavior

Per RFC 6749 §4.4.3, the server **SHOULD NOT** return a refresh token for a
`client_credentials` response. The library handles this:

- If the response includes a refresh token, normal refresh-token rotation
  applies.
- If the response omits a refresh token (the common case), the library marks
  the token as "no refresh available" internally and re-runs
  `client_credentials` on the next expiry. No user credentials are involved,
  so re-authenticating is cheap.

## Constructing the client explicitly

If you'd rather not use env vars, pass the values as kwargs:

```python
client = GundiClient(
    base_url="https://api.gundiservice.org",
    oauth_issuer="https://auth.gundiservice.org/realms/your-realm",
    oauth_client_id="your-client-id",
    oauth_client_secret="your-client-secret",
    # oauth_audience="your-api-audience",
)
```

The kwargs win over env vars.

## See also

- [Password grant](password-grant.md) for user-facing flows
- [OIDC discovery](oidc-discovery.md) for the issuer-based token endpoint resolution
- [Refresh and errors](refresh-and-errors.md) for token-refresh internals
