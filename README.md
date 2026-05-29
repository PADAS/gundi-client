# Gundi Client v2

An async Python client for the [Gundi](https://www.earthranger.com/) API. Gundi (a.k.a. "The Portal") is a platform for managing wildlife conservation integrations — connecting sensors, cameras, and other data sources to analytical platforms like EarthRanger.

This library provides two clients:
- **`GundiClient`** — query connections, integrations, routes, and traces
- **`GundiDataSenderClient`** — post observations, events, and messages

## Installation

```bash
pip install gundi-client-v2
```

## Quick Start

```python
import asyncio
from gundi_client_v2 import GundiClient

async def main():
    async with GundiClient() as client:
        connection = await client.get_connection_details(
            integration_id="your-integration-uuid"
        )
        print(connection.provider.name)

if __name__ == "__main__":
    asyncio.run(main())
```

Set your credentials via environment variables (see [Configuration](#configuration)) or pass them directly:

```python
client = GundiClient(
    username="you@example.com",
    password="your-password",
    oauth_client_id="your-client-id",
    oauth_audience="your-audience",
    oauth_token_url="https://auth.example.com/.../token",
    base_url="https://api.example.com",
)
```

### End-to-End: List, Get Key, Send Data

```python
import asyncio
from gundi_client_v2 import GundiClient, GundiDataSenderClient

async def main():
    async with GundiClient() as client:
        # 1. List integrations and find yours by name
        my_integration = None
        async for i in client.get_integrations():
            if i.name == "My Integration":
                my_integration = i
                break
        if my_integration is None:
            raise RuntimeError("Integration 'My Integration' not found")

        # 2. Get the API key for that integration
        api_key = await client.get_integration_api_key(
            integration_id=str(my_integration.id)
        )

    # 3. Use the API key to send data
    sender = GundiDataSenderClient(integration_api_key=api_key)
    await sender.post_events(data=[
        {
            "title": "Animal Detected",
            "event_type": "wildlife_sighting_rep",
            "recorded_at": "2024-01-15T10:30:00Z",
            "location": {"lat": -1.286, "lon": 36.817},
            "event_details": {"species": "lion"},
        }
    ])

if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration

Settings can be provided as **environment variables** or **constructor keyword arguments**. The two namespaces differ in several places — see the tables below.

### Environment variables

| Env var | Description | Default |
|---|---|---|
| `GUNDI_USERNAME` | Your Gundi username (email) — required for password grant | — |
| `GUNDI_PASSWORD` | Your Gundi password — required for password grant | — |
| `OAUTH_CLIENT_ID` | OAuth client ID | — |
| `OAUTH_CLIENT_SECRET` | OAuth client secret — required for client-credentials grant | — |
| `OAUTH_ISSUER` | OAuth issuer base URL; token URL is derived as `{OAUTH_ISSUER}/protocol/openid-connect/token`. **Do not include a trailing slash** — the value is not stripped and a trailing slash will produce a double-slash in the derived URL. | — |
| `OAUTH_TOKEN_URL` | Full OAuth token endpoint URL. Takes precedence over the value derived from `OAUTH_ISSUER` when set explicitly in the environment. | — |
| `OAUTH_AUDIENCE` | OAuth audience | — |
| `OAUTH_SCOPE` | OAuth scope | `openid` |
| `GUNDI_API_BASE_URL` | Gundi API base URL | — |
| `SENSORS_API_BASE_URL` | Sensors/routing API base URL (used by `GundiDataSenderClient`) | — |
| `GUNDI_API_SSL_VERIFY` | Verify SSL certificates | `true` |
| `LOG_LEVEL` | Logging level (env-only) | `INFO` |
| `GUNDI_CLIENT_ENVFILE` | Path to a `.env` file to load (env-only; defaults to `.env` in cwd) | — |

### GundiClient constructor kwargs

| Kwarg | Corresponding env var | Description |
|---|---|---|
| `base_url` | `GUNDI_API_BASE_URL` | Gundi API base URL |
| `use_ssl` | `GUNDI_API_SSL_VERIFY` | Verify SSL certificates |
| `username` | `GUNDI_USERNAME` | Gundi username |
| `password` | `GUNDI_PASSWORD` | Gundi password |
| `oauth_client_id` | `OAUTH_CLIENT_ID` | OAuth client ID |
| `oauth_client_secret` | `OAUTH_CLIENT_SECRET` | OAuth client secret |
| `oauth_token_url` | `OAUTH_TOKEN_URL` | Full OAuth token endpoint URL |
| `oauth_audience` | `OAUTH_AUDIENCE` | OAuth audience |
| `oauth_scope` | `OAUTH_SCOPE` | OAuth scope |
| `max_http_retries` | — | Max HTTP retries (default `5`) |
| `connect_timeout` | — | Connect timeout in seconds (default `3.1`) |
| `data_timeout` | — | Data timeout in seconds (default `20`) |

> **Note:** `OAUTH_ISSUER` has no constructor kwarg counterpart. Set `oauth_token_url` directly when constructing a client programmatically.

### GundiDataSenderClient constructor kwargs

| Kwarg | Corresponding env var | Description |
|---|---|---|
| `integration_api_key` | — | API key for the integration (required) |
| `sensors_api_base_url` | `SENSORS_API_BASE_URL` | Sensors/routing API base URL |

## Authentication

The client supports two authentication modes:

**Password grant (for developers)** — Provide `GUNDI_USERNAME` and `GUNDI_PASSWORD` along with `OAUTH_CLIENT_ID`. This is the recommended approach for external developers.

**Client credentials grant (for services)** — Provide `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET`. This is used by internal backend services.

> **Backward compatibility:** The legacy `KEYCLOAK_*` env var names (`KEYCLOAK_ISSUER`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_AUDIENCE`) are still accepted as fallbacks for the corresponding `OAUTH_*` env vars. Three legacy constructor kwargs are also still accepted: `keycloak_client_id`, `keycloak_client_secret`, and `keycloak_audience`. There is no `keycloak_issuer` constructor kwarg — use `oauth_token_url` instead.

If both are configured, password grant takes precedence. Contact the Gundi team for credentials.

## Usage: GundiClient

Use `GundiClient` as an async context manager to query the Gundi API.

```python
import asyncio
from gundi_client_v2 import GundiClient

async def main():
    async with GundiClient() as client:
        # List integrations you have access to (async generator — paginated)
        async for integration in client.get_integrations():
            print(integration.name, integration.id)

        # Find an integration by name and get its API key
        target = None
        async for i in client.get_integrations():
            if i.name == "My Integration":
                target = i
                break
        if target is None:
            raise RuntimeError("Integration 'My Integration' not found")
        api_key = await client.get_integration_api_key(
            integration_id=str(target.id)
        )

        # List connections
        connections = await client.get_connections()

        # Get connection details
        connection = await client.get_connection_details(
            integration_id="some-uuid"
        )

        # Get integration details
        integration = await client.get_integration_details(
            integration_id="some-uuid"
        )

        # Get route details
        route = await client.get_route_details(route_id="some-uuid")

        # Query traces
        traces = await client.get_traces(params={"object_id": "some-uuid"})

        # Register an integration type
        integration_type = await client.register_integration_type(
            data={"name": "MyIntegration", "value": "my_integration"}
        )

if __name__ == "__main__":
    asyncio.run(main())
```

You can also create a client without a context manager and close it manually:

```python
import asyncio
from gundi_client_v2 import GundiClient

async def main():
    client = GundiClient()
    try:
        connection = await client.get_connection_details(
            integration_id="some-uuid"
        )
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## Usage: GundiDataSenderClient

Use `GundiDataSenderClient` to post data through the Gundi sensors/routing API. This client authenticates with an integration API key rather than user credentials.

```python
import asyncio
from gundi_client_v2 import GundiDataSenderClient

async def main():
    sender = GundiDataSenderClient(integration_api_key="your-api-key")

    # Post observations
    await sender.post_observations(data=[
        {
            "source": "device-123",
            "source_name": "GPS Tracker",
            "type": "tracking-device",
            "recorded_at": "2024-01-15T10:30:00Z",
            "location": {"lat": -1.286389, "lon": 36.817223},
        }
    ])

    # Post events
    await sender.post_events(data=[
        {
            "title": "Animal Detected",
            "event_type": "wildlife_sighting_rep",
            "recorded_at": "2024-01-15T10:30:00Z",
            "location": {"lat": -1.286389, "lon": 36.817223},
            "event_details": {"species": "lion"},
        }
    ])

    # Post messages
    await sender.post_messages(data=[
        {
            "sender": "ranger-radio-1",
            "recipients": ["hq@example.org"],
            "text": "All clear at checkpoint.",
            "recorded_at": "2024-01-15T10:30:00Z",
        }
    ])

    # Update an event
    await sender.update_event(
        event_id="event-uuid",
        data={"title": "Updated Title"},
    )

    # Post event attachments
    with open("photo.jpg", "rb") as f:
        await sender.post_event_attachments(
            event_id="event-uuid",
            attachments=[("photo.jpg", f.read())],
        )

if __name__ == "__main__":
    asyncio.run(main())
```

## Error Handling

The client raises specific exceptions for different failure modes:

```python
import asyncio
from gundi_client_v2 import GundiClient, AuthenticationError, GundiAPIError, GundiClientError

async def main():
    async with GundiClient() as client:
        try:
            connection = await client.get_connection_details(
                integration_id="some-uuid"
            )
        except AuthenticationError as e:
            # OAuth token request failed (bad credentials, expired, etc.)
            print(f"Auth failed: {e}")
        except GundiAPIError as e:
            # Non-2xx response from the API
            print(f"API error {e.status_code}: {e.detail}")
        except GundiClientError as e:
            # Base exception for all client errors
            print(f"Client error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

## License

Apache 2.0
