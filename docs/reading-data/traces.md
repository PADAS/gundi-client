# Reading Traces

A **Trace** is the record Gundi writes each time a payload crosses a
provider → destination edge. Traces let you confirm delivery, diagnose errors,
and look up the ID the destination assigned to a forwarded observation or event.

For the conceptual background — how payloads move through Gundi and why Traces
exist — see [Tracing and lifecycle](../concepts/tracing-lifecycle.md). This
page covers the API.

| Method | Returns | Notes |
|---|---|---|
| `get_traces(params)` | `List[GundiTrace]` | First page only. |

## Listing traces

```python
import asyncio
from gundi_client_v2 import GundiClient


async def main():
    async with GundiClient() as client:
        traces = await client.get_traces(params={
            "object_id": "<gundi-observation-id>",
        })
        for t in traces:
            print(t.object_id, "→", t.destination, t.delivered_at)


asyncio.run(main())
```

`get_traces()` returns the first page of results only. The default page size
is 20. Pass cursor parameters in `params` to walk additional pages if your
query matches more results than fit in one page.

## Common filters

`get_traces()` accepts a `params` dict that is passed through to the API as
query-string parameters. Useful filters:

```python
# All traces for a specific payload
traces = await client.get_traces(params={"object_id": "<gundi-object-id>"})

# Traces going to a specific destination Integration
# Note: the parameter name is deployment-dependent — try "destination" first;
# some API versions expose it as "destination_id".
traces = await client.get_traces(params={"destination": "<destination-integration-id>"})

# Traces from a specific provider Integration
traces = await client.get_traces(params={"data_provider": "<provider-integration-id>"})

# Only traces that errored
traces = await client.get_traces(params={"has_error": True})

# Combine filters — the API treats multiple keys as AND
traces = await client.get_traces(params={
    "destination": "<destination-integration-id>",
    "has_error": True,
})
```

Time-range filters (e.g. `delivered_at__gte`) may be available depending on
your Gundi deployment version. Consult your deployment's API documentation for
the complete filter surface.

## The `GundiTrace` model

Defined in `gundi_core.schemas.v2.GundiTrace`. Fields:

| Field | Type | Description |
|---|---|---|
| `object_id` | `Union[UUID, str]` | Gundi-side ID of the source observation/event |
| `object_type` | `str` | Payload type discriminator |
| `related_to` | `Optional[Union[UUID, str]]` | Parent object ID |
| `data_provider` | `Optional[Union[UUID, str]]` | Provider Integration ID |
| `destination` | `Optional[Union[UUID, str]]` | Destination Integration ID |
| `delivered_at` | `datetime` | When the payload reached the destination |
| `external_id` | `Optional[Union[UUID, str]]` | The ID assigned by the destination |
| `created_at` | `datetime` | When Gundi recorded the trace |
| `updated_at` | `datetime` | Last update to the trace |
| `last_update_delivered_at` | `datetime` | Time of the most recent successful update |
| `is_duplicate` | `bool` | True if Gundi suppressed as duplicate |
| `has_error` | `bool` | True if delivery errored |

For the canonical field list, see the
[`gundi-core` source](https://github.com/PADAS/gundi-core/blob/main/gundi_core/schemas/v2/gundi.py).

## Use cases

### Confirm a specific observation was delivered

Filter by `object_id` and inspect each trace's status flags:

```python
traces = await client.get_traces(params={"object_id": "<gundi-object-id>"})

for t in traces:
    if t.is_duplicate:
        print(f"Suppressed as duplicate at {t.destination}")
    elif t.has_error:
        print(f"Delivery to {t.destination} errored")
    else:
        print(f"Delivered to {t.destination} at {t.delivered_at}")
```

### Find all errors for a destination

Combine `destination` and `has_error` to pull the error queue for a single
destination Integration:

```python
error_traces = await client.get_traces(params={
    "destination": "<destination-integration-id>",
    "has_error": True,
})
for t in error_traces:
    print(t.object_id, t.object_type)
```

### Look up the destination's external ID for a Gundi observation

After Gundi delivers a payload, the destination assigns its own ID (for
example an EarthRanger event UUID). Retrieve it via `external_id`:

```python
traces = await client.get_traces(params={"object_id": "<gundi-object-id>"})

for t in traces:
    if t.external_id and not t.has_error:
        print(f"Destination {t.destination} assigned ID: {t.external_id}")
```

Use `external_id` to correlate Gundi-side `object_id` values with
destination-side records without querying the destination directly.

## Output as JSON

```python
import json

traces = await client.get_traces(params={"object_id": "<gundi-object-id>"})
print(json.dumps([t.dict() for t in traces], default=str, indent=2))
```

## See also

- [Tracing and lifecycle](../concepts/tracing-lifecycle.md) — how payloads
  move through Gundi and why Traces are recorded
