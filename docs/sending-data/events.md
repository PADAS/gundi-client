# Sending Events

Events represent discrete incidents or reports — wildlife sightings, security alerts, ranger activities, etc. Use `GundiDataSenderClient.post_events()` to push them into Gundi, and `update_event()` to patch an existing event.

## Prerequisites

You need a **provider Integration API key** to authenticate with the Sensors API. Retrieve it via `GundiClient.get_integration_api_key()` using the UUID of the relevant provider integration.

See [Reading — Integrations](../reading-data/integrations.md) for how to look up integration IDs and call `get_integration_api_key`.

!!! warning "API key may be `None`"
    `get_integration_api_key` returns `None` when no API key has been configured for the integration. Always check before proceeding:

    ```python
    api_key = await portal.get_integration_api_key(integration_id="...")
    if api_key is None:
        raise RuntimeError("No API key configured for this integration")
    ```

## Minimal example

```python
import asyncio
from gundi_client_v2 import GundiClient, GundiDataSenderClient


async def main():
    async with GundiClient() as portal:
        api_key = await portal.get_integration_api_key(
            integration_id="<your-provider-integration-id>"
        )
        if api_key is None:
            raise RuntimeError("No API key configured for this integration")

    async with GundiDataSenderClient(integration_api_key=api_key) as sender:
        response = await sender.post_events(data=[
            {
                "event_type": "wildlife_sighting",
                "recorded_at": "2026-06-01T12:34:56Z",
                "location": {"latitude": -1.234, "longitude": 36.789},
                "title": "Elephant near camp",
                "event_details": {
                    "species": "African elephant",
                    "count": 3,
                },
            },
        ])
        print(response)


asyncio.run(main())
```

## Common event fields

| Field | Required | Notes |
|---|---|---|
| `event_type` | Yes | Event-type slug defined by your Gundi deployment |
| `recorded_at` | Yes | ISO-8601 timestamp |
| `location` | Yes | `{"latitude": float, "longitude": float}` |
| `title` | Recommended | Human-readable summary |
| `event_details` | Optional | Free-form dict matching the event-type schema |
| `priority` | Optional | Numeric priority (0 = lowest) |
| `state` | Optional | `new`, `active`, `resolved`, etc. |

!!! tip "Event types are deployment-specific"
    The set of valid `event_type` slugs and the expected `event_details` schema are defined by your Gundi deployment and destination. Check the destination's documentation for the full list.

## Updating an existing event

Use `update_event(event_id, data)` (PATCH) to modify a previously posted event. Pass the Gundi-side `object_id` returned by a successful `post_events` call (or fetched via `get_traces`):

```python
updated = await sender.update_event(
    event_id="<gundi-event-object-id>",
    data={"state": "resolved"},
)
```

!!! note "object_id vs external_id"
    `event_id` is Gundi's internal `object_id`. The destination system's own ID is stored separately in the Trace record as `external_id` and is not used here.

## Sending event attachments

To attach files (photos, documents) to an existing event, see [Sending Messages and Attachments](messages-attachments.md#sending-an-attachment).

## Error handling

Wrap calls in a `try/except` block to catch API errors:

```python
from gundi_client_v2.errors import GundiAPIError

try:
    response = await sender.post_events(data=[...])
except GundiAPIError as exc:
    print(f"Gundi API error {exc.status_code}: {exc}")
```

`GundiDataSenderClient` uses a fixed **120-second** HTTPX timeout.

See [Error handling](../recipes/error-handling.md) for the full pattern and a list of exception types.

## Related

- [Payload types](../concepts/payload-types.md) — overview of observations, events, and messages
- [Sending Observations](observations.md)
- [Sending Messages and Attachments](messages-attachments.md)
