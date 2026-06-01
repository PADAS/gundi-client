# Reading Connections

A **Connection** groups one or more provider Integrations with their
destination Integrations and the Routes between them. See
[Gundi data model](../concepts/data-model.md) for the conceptual overview.

The client exposes two methods for reading Connections:

| Method | Returns | Notes |
|---|---|---|
| `get_connections(params=None)` | `List[Connection]` | Lists all Connections accessible to the authenticated principal |
| `get_connection_details(integration_id)` | `Connection` | Fetches a single Connection by its provider Integration's ID |

## List all connections

```python
import asyncio
from gundi_client_v2 import GundiClient


async def main():
    async with GundiClient() as client:
        connections = await client.get_connections()
        for c in connections:
            print(c.id, c.provider.name, c.status)


asyncio.run(main())
```

## Filtering

`get_connections()` accepts a `params` dict that's passed through to the
API as query-string parameters. Common filters:

```python
# Only healthy connections
healthy = await client.get_connections(params={"status": "healthy"})

# Only connections owned by a specific organization
owned = await client.get_connections(params={"owner": "<organization-id>"})

# Search by name (substring match)
named = await client.get_connections(params={"search": "TrapTagger"})
```

The exact set of available filters depends on the Gundi API version your
deployment exposes. Consult your deployment's API docs for the complete
list; pass anything documented there as a key in `params`.

## Pagination

`get_connections()` does **not** paginate automatically — it returns the
first page of results only. The Gundi API's default page size is currently
20. If your deployment has more Connections than fit in one page and you
need them all, paginate manually using the API's cursor parameters:

```python
all_connections = []
params = {}
while True:
    page = await client.get_connections(params=params)
    all_connections.extend(page)
    # The cursor parameter name depends on your Gundi API version
    # (typically "cursor" or "page"). Check the next/previous links in
    # the raw response if you need to script over multiple pages.
    if len(page) < 20:
        break
    # ... advance cursor
    break
```

For streaming-style iteration over a large result set, prefer
[`get_integrations()`](integrations.md), which is an async generator and
walks pagination cursors transparently.

## Fetch one connection

```python
connection = await client.get_connection_details(
    integration_id="ddd0946d-15b0-4308-b93d-e0470b6d33b6"
)
print(connection.dict())
```

The `integration_id` is the ID of the **provider** Integration. If you don't
have it, list connections and pick the one you want by name or status:

```python
connections = await client.get_connections(params={"status": "healthy"})
target = next(c for c in connections if c.provider.name == "TrapTagger PADAS")
print(target.id)
```

## The `Connection` model

Defined in `gundi_core.schemas.v2.Connection`. Key fields:

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Connection's unique identifier |
| `status` | `str` | `healthy`, `unhealthy`, `disabled`, or `unknown` |
| `provider` | `ConnectionIntegration` | Shallow view of the provider Integration (id, name, type, owner, base_url, status). For the full Integration record use `get_integration_details()`. |
| `destinations` | `List[ConnectionIntegration]` | Shallow views of destination Integrations |
| `routing_rules` | `List[ConnectionRoute]` | Lightweight references to Routes; each has `id` and `name` |
| `default_route` | `Optional[ConnectionRoute]` | The Route used when no other rule matches |
| `owner` | `Organization` | The owning Organization |

For the canonical field list, see the
[`gundi-core` source](https://github.com/PADAS/gundi-core/blob/main/gundi_core/schemas/v2/gundi.py).

## Output as JSON

`Connection` is a Pydantic v1 model — call `.dict()` to get a plain dict, or
serialize directly with `json.dumps`:

```python
import json

connections = await client.get_connections()
print(json.dumps([c.dict() for c in connections], default=str, indent=2))
```

`default=str` handles `UUID`, `datetime`, and other non-JSON-native types.

## See also

- [Reading Integrations](integrations.md) for individual provider/destination details
- [Connection example script](https://github.com/PADAS/gundi-client/blob/v2/examples/list_connections_client_credentials.py) in the repo
