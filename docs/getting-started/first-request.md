# First request

This page walks through a minimal end-to-end example: authenticate and list
the Connections in your Gundi account. If you haven't yet set environment
variables, do [Authentication setup](auth-setup.md) first.

## Smoke test

Save this as `smoke.py` in the same directory as your `.env`:

```python
import asyncio
import json
from gundi_client_v2 import GundiClient


async def main():
    async with GundiClient() as client:
        connections = await client.get_connections()
        print(f"Found {len(connections)} connections")
        if connections:
            # Print the first one as JSON
            print(json.dumps(connections[0].dict(), default=str, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
```

Run it:

```bash
python smoke.py
```

You should see a connection count and a JSON dump of the first Connection.

## What just happened

1. **`GundiClient()`** read your env vars (`GUNDI_API_BASE_URL`,
   `OAUTH_ISSUER`, and the credentials) into a configured client.
2. **`async with`** opened the underlying HTTPX session. No network
   traffic yet.
3. **`client.get_connections()`** triggered the first authenticated
   request. The client fetched the IdP's
   `/.well-known/openid-configuration` document (OIDC discovery),
   obtained an access token, then GET'd `/v2/connections/` on your
   Gundi API and parsed the response into a list of `Connection`
   Pydantic models.
4. **Exiting the context** closed the HTTPX session cleanly.

## Filtering and pagination

`get_connections()` accepts a `params` dict that's passed straight to the
API as query-string parameters. For example, filtering to only "healthy"
connections (other status values include `unhealthy` and `disabled`):

```python
healthy = await client.get_connections(params={"status": "healthy"})
```

For the full set of filters and pagination patterns, see
[Reading data → Connections](../reading-data/connections.md).

## Next

- Learn how Gundi models its data → [Gundi data model](../concepts/data-model.md)
- Dive into the auth grants → [Authentication overview](../authentication/overview.md)
- See more `Connection` examples → [Reading Connections](../reading-data/connections.md)
