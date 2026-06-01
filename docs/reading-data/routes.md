# Reading Routes

A **Route** maps one or more provider Integrations to destination Integrations
and optionally transforms payloads in transit (typically via a JQ filter). See
[Gundi data model](../concepts/data-model.md) for the conceptual overview.

The client exposes a full CRUD surface for Routes:

| Method | Returns | Notes |
|---|---|---|
| `get_routes(params=None)` | `List[Route]` | First page only. |
| `get_route_details(route_id)` | `Route` | Fetches by ID. |
| `get_routes_for_connection(connection_id)` | `List[Route]` | Convenience wrapper for `get_routes(params={"provider": connection_id})`. First page only. |
| `create_route(data)` | `Route` | POST. |
| `update_route(route_id, data)` | `Route` | PATCH (partial updates supported). |
| `delete_route(route_id)` | `None` | DELETE; returns None on success. |

## List routes

```python
import asyncio
from gundi_client_v2 import GundiClient


async def main():
    async with GundiClient() as client:
        routes = await client.get_routes()
        for r in routes:
            print(r.id, r.name, len(r.data_providers), "provider(s)")


asyncio.run(main())
```

`get_routes()` returns the first page of results only. The Gundi API's default
page size is 20. If you need to walk multiple pages, pass the cursor parameters
your deployment exposes in `params`. For streaming over a large result set,
prefer [`get_integrations()`](integrations.md), which is an async generator.

## Filtering

`get_routes()` accepts a `params` dict that is forwarded to the API as
query-string parameters. Common filters:

```python
# Routes where a specific Integration is a provider
provider_routes = await client.get_routes(
    params={"provider": "<provider-integration-id>"}
)

# Routes that deliver to a specific destination
dest_routes = await client.get_routes(
    params={"destination": "<destination-integration-id>"}
)

# Routes owned by a specific organization
org_routes = await client.get_routes(
    params={"owner": "<organization-id>"}
)
```

`get_routes_for_connection(connection_id)` is a convenience wrapper that calls
`get_routes(params={"provider": str(connection_id)})` for you.

## Fetch one route

```python
route = await client.get_route_details(
    route_id="a1b2c3d4-0000-0000-0000-000000000000"
)
print(route.name, route.configuration)
```

## Create a route

`create_route()` accepts a dict whose shape follows the Gundi API's route
creation endpoint. The `data_providers` and `destinations` fields take
**raw Integration IDs** (strings or UUIDs) in the input dict:

```python
route = await client.create_route(data={
    "name": "TrapTagger → ER (events)",
    "owner": "<organization-id>",
    "data_providers": ["<provider-integration-id>"],
    "destinations": ["<destination-integration-id>"],
})
print(route.id)
```

The returned `Route` object has `data_providers` and `destinations` populated
as `ConnectionIntegration` objects (not raw IDs). The same applies to
`update_route()`.

## Update a route

`update_route()` uses HTTP PATCH, so you can send a partial dict — only the
fields you include are changed:

```python
route = await client.update_route(
    route_id="<route-id>",
    data={"name": "Renamed"},
)
print(route.name)
```

You can update any of the writable fields via the same partial-dict pattern.
For transformation logic (the `configuration` field), the inner `data` shape is
deployment-specific — consult your deployment's documentation for the exact
structure.

## Delete a route

```python
await client.delete_route(route_id=route.id)
# Returns None on success (HTTP 204 No Content)
```

`delete_route()` returns `None` on success. There is no response body to
inspect. If the route does not exist or you do not have permission to delete
it, a `GundiAPIError` is raised.

## The `Route` model

Defined in `gundi_core.schemas.v2.Route`. Key fields:

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Route ID |
| `name` | `str` | Human-readable name |
| `owner` | `Optional[UUID]` | Organization ID |
| `data_providers` | `List[ConnectionIntegration]` | Provider Integrations |
| `destinations` | `List[ConnectionIntegration]` | Destination Integrations |
| `configuration` | `RouteConfiguration` | Transformation rules (often a JQ filter) |
| `additional` | `Dict[str, Any]` | Free-form extras |

`ConnectionIntegration` is the same shallow view used in the `Connection`
model: it carries `id`, `name`, `type`, `owner`, `base_url`, and `status`.
For the full Integration record, call
[`get_integration_details()`](integrations.md).

For the canonical field list, see the
[`gundi-core` source](https://github.com/PADAS/gundi-core/blob/main/gundi_core/schemas/v2/gundi.py).

## Output as JSON

```python
import json

routes = await client.get_routes()
print(json.dumps([r.dict() for r in routes], default=str, indent=2))
```

`default=str` handles `UUID` and other non-JSON-native types that Pydantic v1
stores as objects.

## See also

- [Gundi data model](../concepts/data-model.md) — Integration, Connection, and
  Route vocabulary
- [Reading Connections](connections.md) — Connections group providers and
  destinations; Routes define the wiring between them
- [Reading Integrations](integrations.md) — fetch full Integration details from
  the IDs in `data_providers` / `destinations`
