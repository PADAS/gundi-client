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
2. **`async with`** entered the client's async context. The first network
   call triggers OIDC discovery (fetch
   `{OAUTH_ISSUER}/.well-known/openid-configuration`) and obtains an
   access token.
3. **`client.get_connections()`** GETs `/v2/connections/` on your
   Gundi API, parses the response into `Connection` Pydantic models, and
   returns them as a list.
4. **Exiting the context** closes the underlying HTTPX session cleanly.

## Filtering and pagination

`get_connections()` accepts a `params` dict that's passed straight to the
API as query-string parameters:

```python
healthy = await client.get_connections(params={"status": "healthy"})
```

For full filter coverage and pagination patterns, see
[Reading data → Connections](../reading-data/connections.md).

## Next

- Learn how Gundi models its data → [Gundi data model](../concepts/data-model.md)
- Dive into the auth grants → [Authentication overview](../authentication/overview.md)
- See more `Connection` examples → [Reading Connections](../reading-data/connections.md)
