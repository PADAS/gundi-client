# Sending Messages and Attachments

Gundi supports two distinct operations for sending supplemental data alongside observations and events:

- **Messages** — text messages sent via `post_messages()`, with optional location and timestamp
- **Attachments** — binary files (images, documents) attached to an existing event via `post_event_attachments()`

These use different methods and different payload shapes.

## Prerequisites

You need a **provider Integration API key** to authenticate with the Sensors API. Retrieve it via `GundiClient.get_integration_api_key()`.

See [Reading — Integrations](../reading-data/integrations.md) for how to look up integration IDs.

!!! warning "API key may be `None`"
    `get_integration_api_key` returns `None` when no API key has been configured for the integration. Always check before proceeding:

    ```python
    api_key = await portal.get_integration_api_key(integration_id="...")
    if api_key is None:
        raise RuntimeError("No API key configured for this integration")
    ```

## Sending a message

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
        response = await sender.post_messages(data=[
            {
                "sender": "ranger-1",
                "recipients": ["ops-channel"],
                "text": "Camera trap triggered at site B.",
                # Optional:
                # "recorded_at": "2026-06-01T12:34:56Z",
                # "location": {"latitude": -1.234, "longitude": 36.789},
                # "additional": {"status": {"lowBattery": 1}},
            },
        ])
        print(response)


asyncio.run(main())
```

### Message fields

| Field | Required | Notes |
|---|---|---|
| `sender` | Yes | Identifier for the message sender |
| `recipients` | Yes | List of recipient identifiers |
| `text` | Yes | The message body |
| `recorded_at` | Optional | ISO-8601 timestamp; defaults to ingestion time if omitted |
| `location` | Optional | `{"latitude": float, "longitude": float}` |
| `additional` | Optional | Free-form dict of additional attributes |

Note that `recipients` is a **list** — even when targeting a single channel or address, wrap it in a list.

## Sending an attachment

Attachments are binary files associated with a specific event. Use `post_event_attachments(event_id, attachments)` where each attachment is a `(filename, file_binary)` tuple:

```python
with open("photo.jpg", "rb") as f:
    binary = f.read()

async with GundiDataSenderClient(integration_api_key=api_key) as sender:
    response = await sender.post_event_attachments(
        event_id="<gundi-event-object-id>",
        attachments=[("photo.jpg", binary)],
    )
```

To send multiple attachments in a single call, add more tuples to the list:

```python
response = await sender.post_event_attachments(
    event_id="<gundi-event-object-id>",
    attachments=[
        ("photo1.jpg", binary1),
        ("photo2.jpg", binary2),
    ],
)
```

!!! note "What gets sent on the wire"
    Attachments are uploaded as a **multipart form request**. Each tuple becomes a `file` form field using the provided filename as the `Content-Disposition` filename.

## Limits

`GundiDataSenderClient` uses a fixed **120-second** HTTPX timeout. For large files:

- Split the upload across multiple calls (one attachment at a time)
- Upload the file to external storage and reference the URL from the event's `event_details` field

## Error handling

```python
from gundi_client_v2.errors import GundiAPIError

try:
    response = await sender.post_event_attachments(event_id="...", attachments=[...])
except GundiAPIError as exc:
    print(f"Gundi API error {exc.status_code}: {exc}")
```

See [Error handling](../recipes/error-handling.md) for the full pattern and a list of exception types.

## Related

- [Payload types](../concepts/payload-types.md) — overview of observations, events, and messages
- [Sending Observations](observations.md)
- [Sending Events](events.md)
