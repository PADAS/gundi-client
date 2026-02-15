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
from gundi_client_v2 import GundiClient

async with GundiClient() as client:
    connection = await client.get_connection_details(
        integration_id="your-integration-uuid"
    )
    print(connection.provider.name)
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
from gundi_client_v2 import GundiClient, GundiDataSenderClient

async with GundiClient() as client:
    # 1. List integrations and find yours by name
    integrations = await client.get_integrations()
    my_integration = next(i for i in integrations if i.name == "My Integration")

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
```

## Configuration

All settings can be provided as environment variables or keyword arguments to the client constructor.

### Developer Authentication

| Variable | Description | Required |
|---|---|---|
| `GUNDI_USERNAME` | Your Gundi username (email) | Yes (for password auth) |
| `GUNDI_PASSWORD` | Your Gundi password | Yes (for password auth) |

### Service Authentication

| Variable | Description | Required |
|---|---|---|
| `OAUTH_CLIENT_ID` | OAuth client ID | Yes |
| `OAUTH_CLIENT_SECRET` | OAuth client secret | Yes (for client credentials auth) |

### Common

| Variable | Description | Default |
|---|---|---|
| `OAUTH_ISSUER` | OAuth issuer URL (token URL is derived as `{issuer}/protocol/openid-connect/token`) | — |
| `OAUTH_AUDIENCE` | OAuth audience | — |
| `GUNDI_API_BASE_URL` | Gundi API base URL | — |
| `SENSORS_API_BASE_URL` | Sensors/routing API base URL | — |
| `GUNDI_API_SSL_VERIFY` | Verify SSL certificates | `true` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Authentication

The client supports two authentication modes:

**Password grant (for developers)** — Provide `GUNDI_USERNAME` and `GUNDI_PASSWORD` along with `OAUTH_CLIENT_ID`. This is the recommended approach for external developers.

**Client credentials grant (for services)** — Provide `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET`. This is used by internal backend services.

> **Note:** The legacy `KEYCLOAK_*` env var names (`KEYCLOAK_ISSUER`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_AUDIENCE`) and `keycloak_*` constructor kwargs are still accepted for backward compatibility.

If both are configured, password grant takes precedence. Contact the Gundi team for credentials.

## Usage: GundiClient

Use `GundiClient` as an async context manager to query the Gundi API.

```python
from gundi_client_v2 import GundiClient

async with GundiClient() as client:
    # List integrations you have access to
    integrations = await client.get_integrations()
    for integration in integrations:
        print(integration.name, integration.id)

    # Find an integration by name and get its API key
    target = next(i for i in integrations if i.name == "My Integration")
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
```

You can also create a client without a context manager and close it manually:

```python
client = GundiClient()
try:
    connection = await client.get_connection_details(
        integration_id="some-uuid"
    )
finally:
    await client.close()
```

## Usage: GundiDataSenderClient

Use `GundiDataSenderClient` to post data through the Gundi sensors/routing API. This client authenticates with an integration API key rather than user credentials.

```python
from gundi_client_v2 import GundiDataSenderClient

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
```

## Error Handling

The client raises specific exceptions for different failure modes:

```python
from gundi_client_v2 import GundiClient, AuthenticationError, GundiAPIError, GundiClientError

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
```

## License

Apache 2.0
