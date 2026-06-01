# Sending Observations

Observations are timestamped, geo-located data points — typically position fixes from tracking devices. Use `GundiDataSenderClient.post_observations()` to push them into Gundi.

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

    sender = GundiDataSenderClient(integration_api_key=api_key)
    response = await sender.post_observations(data=[
        {
            "source": "device-001",
            "type": "tracking-device",
            "subject_type": "wildlife.elephant",
            "recorded_at": "2026-06-01T12:34:56Z",
            "location": {"lat": -1.234, "lon": 36.789},
            "additional": {"battery_voltage": 3.9},
        },
    ])
    print(response)


asyncio.run(main())
```

!!! note "Session lifetime"
    Unlike `GundiClient`, `GundiDataSenderClient` is **not** an async context manager — it doesn't hold a persistent session. Instantiate it directly and `await` its methods.

## Sending multiple observations

Pass a list with as many dicts as you like. All items are submitted in a single request:

```python
response = await sender.post_observations(data=[
    {"source": "device-001", "recorded_at": "...", ...},
    {"source": "device-002", "recorded_at": "...", ...},
])
```

!!! note "Rate limits"
    Very large batches may hit per-deployment rate limits. Check your Gundi deployment's documentation for the recommended batch ceiling.

## Required and common fields

| Field | Required | Notes |
|---|---|---|
| `source` | Yes | Device identifier — typically the source's ID at the provider |
| `type` | Yes | `tracking-device`, `stationary-object`, `ranger-radio-position`, etc. |
| `recorded_at` | Yes | ISO-8601 timestamp |
| `location` | Yes | `{"lat": float, "lon": float}` |
| `subject_type` | Recommended | Helps the destination categorize the source |
| `additional` | Optional | Free-form dict of additional attributes |

!!! tip "Schema is destination-defined"
    Gundi forwards what it receives (potentially through a Route's transformation). Refer to your destination's documentation for the full accepted schema.

## The response

`post_observations` returns the raw JSON the API returned — typically a list where each item contains the Gundi-assigned `object_id` and `created_at` timestamp:

```json
[
    {
        "object_id": "96422ba3-3ea9-4b0d-8950-850e218e1140",
        "created_at": "2026-06-01T12:34:09.539777Z"
    }
]
```

The exact shape may vary by deployment.

## Error handling

Wrap calls in a `try/except` block to catch API errors:

```python
from gundi_client_v2.errors import GundiAPIError

try:
    response = await sender.post_observations(data=[...])
except GundiAPIError as exc:
    print(f"Gundi API error {exc.status_code}: {exc}")
```

`GundiDataSenderClient` uses a fixed **120-second** HTTPX timeout. If your deployment is slow to respond, consider splitting large batches into smaller ones.

See [Error handling](../recipes/error-handling.md) for the full pattern and a list of exception types.

## Related

- [Payload types](../concepts/payload-types.md) — overview of observations, events, and messages
- [Sending Events](events.md)
- [Sending Messages and Attachments](messages-attachments.md)
