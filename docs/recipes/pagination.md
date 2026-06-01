# Pagination

The Gundi client handles pagination differently depending on the method
you're calling. `get_integrations()` walks all pages automatically;
`get_connections()` and `get_routes()` return only the first page.

## `get_integrations()` — automatic cursor walking

`get_integrations()` is an **async generator** that transparently follows
the Gundi API's `next` cursor. You iterate with `async for` and the client
fetches subsequent pages on demand.

```python
import asyncio
from gundi_client_v2 import GundiClient


async def main():
    async with GundiClient() as client:
        async for integration in client.get_integrations(params={"search": "lotek"}):
            print(integration.id, integration.name)


asyncio.run(main())
```

You can also materialize all results at once:

```python
async with GundiClient() as client:
    integrations = [i async for i in client.get_integrations()]
```

Note that materializing large result sets into a list consumes memory
proportional to the total count. For large deployments, prefer streaming
with `async for`.

## `get_connections()` and `get_routes()` — first page only

`get_connections()` and `get_routes()` parse and return only the items
from the first page of results.

For these two methods, you'll need to handle pagination yourself. The
Gundi API uses cursor-based pagination — the response includes a `next`
URL when more pages exist — but `get_connections()` and `get_routes()`
parse and return only the items from the first page. If you need to
walk multiple pages, two options:

1. **Increase the page size via a query parameter** (the exact parameter
   name varies by deployment — typically `limit` or `page_size`). This
   is the simplest fix when your dataset is small to medium.

2. **Drop down to the raw HTTPX session** on the client (`client._session`)
   to call the endpoint directly, then walk the `next` URL yourself.
   This bypasses the convenience method but lets you stream results.

!!! warning "`_session` is private API"
    The `_session` attribute is an internal implementation detail and may
    change between releases without notice. Treat this as a last-resort
    workaround until the library exposes a public pagination helper.

See also [Filtering](filtering.md) for ways to narrow the result set
before it reaches the pagination layer.

## Trade-offs

| Approach | Pro | Con |
|---|---|---|
| `async for` generator | Low memory; streams results | Cannot `len()` without materializing |
| List comprehension (`[i async for i in ...]`) | Random access, slicing | Holds all results in RAM |
| Manual `_session` walk | Full control over cursor | Bypasses type parsing; more code |

## Related pages

- [Reading Connections](../reading-data/connections.md)
- [Reading Integrations](../reading-data/integrations.md)
- [Reading Routes](../reading-data/routes.md)
