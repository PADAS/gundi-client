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
            print(c.id, c.name, c.status)


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

`get_connections()` handles pagination transparently — it walks the
`next` cursor from the API's paginated response and returns the
**accumulated list**.

For large result sets where you want streaming behavior, fall back to
manual pagination by passing the cursor parameters explicitly through
`params`.

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
target = next(c for c in connections if c.name == "TrapTagger PADAS")
print(target.id)
```

## The `Connection` model

Defined in `gundi_core.schemas.v2.Connection`. Key fields:

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Connection's unique identifier |
| `name` | `str` | Human-readable name |
| `status` | `str` | `healthy`, `unhealthy`, `disabled` |
| `provider` | `Integration` | The provider Integration |
| `destinations` | `List[Integration]` | One or more destination Integrations |
| `routing_rules` | `List[UUID]` | Route IDs that apply to this Connection |
| `default_route` | `Optional[UUID]` | The default Route ID, if any |
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
