# Reading Integrations

An **Integration** is a single registered third-party system — either a
provider (e.g. a TrapTagger camera trap) or a destination (e.g. an
EarthRanger site). See [Gundi data model](../concepts/data-model.md) for
context.

The client exposes three methods:

| Method | Returns | Notes |
|---|---|---|
| `get_integrations(params=None)` | `AsyncGenerator[Integration, None]` | Streams all Integrations matching the filters |
| `get_integration_details(integration_id)` | `Integration` | Fetches one Integration by ID |
| `get_integration_api_key(integration_id)` | `str` | The Integration's API key. Used to bootstrap a `GundiDataSenderClient`. |

## List integrations (async generator)

Unlike `get_connections`, `get_integrations` is an **async generator** —
iterate it with `async for`:

```python
import asyncio
from gundi_client_v2 import GundiClient


async def main():
    async with GundiClient() as client:
        async for integration in client.get_integrations():
            print(integration.id, integration.name, integration.type)


asyncio.run(main())
```

Why a generator? The Integrations endpoint paginates aggressively for large
deployments. Streaming lets your code start processing as the first page
arrives rather than waiting for the full list.

If you need a list anyway, materialize it:

```python
integrations = [i async for i in client.get_integrations()]
```

!!! note "Don't `await` the generator itself"
    `get_integrations()` returns an async generator, not a coroutine. Use
    `async for` or an async list comprehension. `await client.get_integrations()`
    will fail at runtime.

## Filtering

```python
# Only provider-type Integrations
async for i in client.get_integrations(params={"action_type": "pull_observations"}):
    print(i.name)

# Search by name substring
async for i in client.get_integrations(params={"search": "lotek"}):
    print(i.name, i.id)
```

Consult your Gundi API's documentation for the full set of filter keys.

## Fetch one integration

```python
integration = await client.get_integration_details(
    integration_id="338225f3-91f9-4fe1-b013-353a229ce504"
)
print(integration.dict())
```

## Get an Integration's API key

Some workflows need the per-Integration API key to send observations or
events directly through Gundi's data ingestion API. Fetch it with:

```python
api_key = await client.get_integration_api_key(
    integration_id="338225f3-91f9-4fe1-b013-353a229ce504"
)
```

Then pass it to `GundiDataSenderClient`:

```python
from gundi_client_v2 import GundiDataSenderClient

async with GundiDataSenderClient(integration_api_key=api_key) as sender:
    await sender.post_observations(data=[{...}])
```

(Sending observations is covered in Phase 2 of these docs.)

## The `Integration` model

Defined in `gundi_core.schemas.v2.Integration`. Key fields:

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Integration's unique identifier |
| `name` | `str` | Human-readable name |
| `type` | `IntegrationType` | Slug + display name of the system type |
| `base_url` | `str` | URL of the third-party system, if applicable |
| `enabled` | `bool` | Whether Gundi is actively pulling/pushing |
| `owner` | `Organization` | The owning Organization |
| `configurations` | `List[IntegrationActionConfiguration]` | Per-action configuration |
| `webhook_configuration` | `Optional[IntegrationWebhookConfiguration]` | Webhook-specific config |

For the canonical field list, see the
[`gundi-core` source](https://github.com/PADAS/gundi-core/blob/main/gundi_core/schemas/v2/gundi.py).

## Output as JSON

```python
import json

integrations = [i async for i in client.get_integrations()]
print(json.dumps([i.dict() for i in integrations], default=str, indent=2))
```

## See also

- [Reading Connections](connections.md) — group Integrations by provider/destination
- [Send observations example](https://github.com/PADAS/gundi-client/blob/v2/examples/send_observations.py)
