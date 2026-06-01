# Filtering

All `get_*` methods on `GundiClient` accept an optional `params` dict
that is forwarded as query parameters to the Gundi API. The API treats
multiple keys in the same dict as AND conditions.

## Status filters

Filter Connections by health status:

```python
async with GundiClient() as client:
    healthy = await client.get_connections(params={"status": "healthy"})
    broken = await client.get_connections(params={"status": "unhealthy"})
```

Valid values for `status`: `healthy`, `unhealthy`, `disabled`, `unknown`.

## Owner filters

Scope results to a specific organization:

```python
async with GundiClient() as client:
    org_connections = await client.get_connections(
        params={"owner": "<organization-id>"}
    )
    org_integrations = [
        i async for i in client.get_integrations(
            params={"owner": "<organization-id>"}
        )
    ]
```

The `owner` filter works across Connections, Integrations, and Routes.

## Substring search

Most list endpoints support a `search` parameter for substring matching
on the resource name:

```python
async with GundiClient() as client:
    async for integration in client.get_integrations(params={"search": "lotek"}):
        print(integration.name)
```

## Provider and destination filters on Routes

Narrow Routes to those involving a specific provider or destination
Integration:

```python
async with GundiClient() as client:
    # Routes where this integration is a provider
    provider_routes = await client.get_routes(
        params={"provider": "<integration-id>"}
    )

    # Routes where this integration is a destination
    dest_routes = await client.get_routes(
        params={"destination": "<integration-id>"}
    )
```

`get_routes_for_connection(connection_id)` is a convenience wrapper for
`get_routes(params={"provider": str(connection_id)})`.

## Trace filters

Common trace queries:

```python
async with GundiClient() as client:
    # All traces for a specific Gundi observation
    traces = await client.get_traces(
        params={"object_id": "<gundi-observation-id>"}
    )

    # All error traces for a provider
    error_traces = await client.get_traces(
        params={"data_provider": "<provider-id>", "has_error": True}
    )
```

## Combining filters

Pass multiple keys in the same dict to AND them together:

```python
async with GundiClient() as client:
    connections = await client.get_connections(
        params={"status": "healthy", "owner": "<organization-id>"}
    )
```

## Client-side filtering

When the server doesn't expose a filter you need, filter the returned
list locally:

```python
async with GundiClient() as client:
    connections = await client.get_connections()
    traptagger = [
        c for c in connections
        if c.provider.name.startswith("TrapTagger")
    ]
```

Client-side filtering only sees the first page of results. If your
dataset spans multiple pages, either increase the page size (see
[Pagination](pagination.md)) or use `get_integrations()` which
walks all pages automatically.

## Related pages

- [Reading Connections](../reading-data/connections.md)
- [Reading Integrations](../reading-data/integrations.md)
- [Reading Routes](../reading-data/routes.md)
- [Reading Traces](../reading-data/traces.md)
- [Pagination](pagination.md)
