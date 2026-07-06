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

Configure the client via environment variables (see [Configuration](#configuration)) or pass values directly. The Quick Start snippet needs more than credentials at runtime — at minimum a `base_url` / `GUNDI_API_BASE_URL`, an `OAUTH_CLIENT_ID`, and either an `OAUTH_ISSUER` or `oauth_token_url`. Example with kwargs:

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
import os
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
    sender = GundiDataSenderClient(
        integration_api_key=api_key,
        sensors_api_base_url=os.environ["SENSORS_API_BASE_URL"],  # or pass the URL directly
    )
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
| `OAUTH_ISSUER` | OIDC issuer URL. When set without `OAUTH_TOKEN_URL`, the token endpoint is discovered at runtime from `{OAUTH_ISSUER}/.well-known/openid-configuration`. A trailing slash is normalized. | — |
| `OAUTH_TOKEN_URL` | Full OAuth token endpoint URL. When set, overrides OIDC discovery from `OAUTH_ISSUER`. | — |
| `OAUTH_AUDIENCE` | OAuth audience. Sent to the token endpoint when set. Required by some IdPs (e.g. Auth0 won't issue a usable API access token without it); ignored by others (Keycloak password grant). | — |
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
| `oauth_token_url` | `OAUTH_TOKEN_URL` | Full OAuth token endpoint URL. When set, used as-is. |
| `oauth_issuer` | `OAUTH_ISSUER` | OIDC issuer URL. When set without `oauth_token_url`, the token endpoint is discovered via OIDC discovery. |
| `oauth_audience` | `OAUTH_AUDIENCE` | OAuth audience. IdP-dependent — required for Auth0, optional for Keycloak password grant. |
| `oauth_scope` | `OAUTH_SCOPE` | OAuth scope |
| `max_http_retries` | — | Max HTTP retries (default `5`) |
| `connect_timeout` | — | Connect timeout in seconds (default `3.1`) |
| `data_timeout` | — | Data timeout in seconds (default `20`) |

### GundiDataSenderClient constructor kwargs

| Kwarg | Corresponding env var | Description |
|---|---|---|
| `integration_api_key` | — | API key for the integration (required) |
| `sensors_api_base_url` | `SENSORS_API_BASE_URL` | Sensors/routing API base URL |

## Authentication

The client supports two authentication modes:

**Password grant (for developers)** — Provide `GUNDI_USERNAME` and `GUNDI_PASSWORD` along with `OAUTH_CLIENT_ID`. This is the recommended approach for external developers.

**Client credentials grant (for services)** — Provide `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET`. This is used by internal backend services.

### Token URL resolution

The client resolves the OAuth token endpoint in this order:

1. **`oauth_token_url` (kwarg) / `OAUTH_TOKEN_URL` (env)** — used as-is when set.
2. **`oauth_issuer` (kwarg) / `OAUTH_ISSUER` (env)** — the client fetches `{issuer}/.well-known/openid-configuration` (OIDC discovery) and uses its `token_endpoint`. Result is cached for the process lifetime; call `gundi_client_v2.auth.clear_discovery_cache()` to invalidate.
3. **Neither set** — `AuthenticationError("No token URL configured. Set oauth_token_url or oauth_issuer.")` is raised on the first auth attempt.

OIDC discovery works for any compliant IdP (Keycloak, Auth0, Okta, …). Configure `OAUTH_ISSUER` and the token endpoint is found automatically.

### Audience

`OAUTH_AUDIENCE` is sent to the token endpoint when configured. Whether it is required depends on the IdP:

- **Auth0** — required. Without `audience`, Auth0 issues an opaque token that cannot authorize API requests.
- **Keycloak** — optional. Both grant types this library supports (password and client_credentials) ignore it.

The parameter name `audience` reflects the Auth0/Keycloak convention. The OAuth 2.0 / OIDC standard equivalent is `resource` (RFC 8707, *Resource Indicators*). If we add support for IdPs that strictly require `resource` instead, it will be introduced as a `resource` kwarg alongside `audience`, not as a rename. Existing `OAUTH_AUDIENCE` / `oauth_audience` configurations will keep working.

> **Backward compatibility:** The legacy `KEYCLOAK_*` env var names (`KEYCLOAK_ISSUER`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_AUDIENCE`) are still accepted as fallbacks for the corresponding `OAUTH_*` env vars. Three legacy constructor kwargs are also still accepted: `keycloak_client_id`, `keycloak_client_secret`, and `keycloak_audience`. There is no `keycloak_issuer` constructor kwarg — use `oauth_token_url` or `oauth_issuer` instead.

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

        # List routes (optionally pass params= for server-side filtering)
        routes = await client.get_routes()

        # List routes where a connection is the data provider
        routes = await client.get_routes_for_connection(
            connection_id="some-provider-uuid"
        )

        # Get route details
        route = await client.get_route_details(route_id="some-uuid")

        # Create a route
        new_route = await client.create_route(data={
            "name": "TrapTagger → ER (events)",
            "owner": "your-org-uuid",
            "data_providers": ["provider-integration-uuid"],
            "destinations": ["destination-integration-uuid"],
        })

        # Update a route (partial update via PATCH)
        updated_route = await client.update_route(
            route_id="some-uuid",
            data={"name": "Renamed Route"},
        )

        # Delete a route
        await client.delete_route(route_id="some-uuid")

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

Use `GundiDataSenderClient` to post data through the Gundi sensors/routing API. This client authenticates with an integration API key rather than user credentials. `sensors_api_base_url` is required — you can set it via the `SENSORS_API_BASE_URL` environment variable (as the example script does) or pass it directly.

```python
import asyncio
import os
from gundi_client_v2 import GundiDataSenderClient

async def main():
    sender = GundiDataSenderClient(
        integration_api_key="your-api-key",
        sensors_api_base_url=os.environ["SENSORS_API_BASE_URL"],  # or pass the URL directly
    )

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

## Command-Line Interface

An optional `gundi` command wraps `GundiClient` for common integration tasks. It
ships in the `cli` extra (keeps Typer out of the core install):

```bash
pip install "gundi-client-v2[cli]"
```

Authentication reuses the same environment variables as the library (see
[Configuration](#configuration)). The CLI needs `GUNDI_API_BASE_URL`,
`OAUTH_CLIENT_ID`, plus:

- **Credentials** — either `GUNDI_USERNAME` + `GUNDI_PASSWORD` (password grant,
  for developers) or `OAUTH_CLIENT_SECRET` (client-credentials, for services).
- **Token endpoint** — `OAUTH_ISSUER` (preferred; resolved via OIDC discovery)
  or an explicit `OAUTH_TOKEN_URL`.

`OAUTH_AUDIENCE` is forwarded when set. A `.env` file in the working directory
is loaded automatically.

```bash
# List all integrations (table: ID, NAME, TYPE, ENABLED, STATUS)
gundi integrations list

# Filter by integration type, by enabled state, and emit JSON for piping to jq
gundi integrations list --type earth_ranger
gundi integrations list --enabled       # only enabled (--disabled for only disabled)
gundi integrations list --status healthy   # by health status (healthy/unhealthy/disabled)
gundi integrations list --type earth_ranger --enabled --status unhealthy
gundi integrations list --json | jq '.[].name'

# List the available integration types (table: NAME, SLUG, ID)
gundi integrations types

# Read the latest activity logs for an integration or a whole type
gundi integrations logs 338225f3-91f9-4fe1-b013-353a229ce504
gundi integrations logs --type earth_ranger --limit 100
# Filter logs by level (matches that level and above), origin, and a date range
gundi integrations logs 338225f3-91f9-4fe1-b013-353a229ce504 --level error
gundi integrations logs --type earth_ranger --level warning --origin dispatcher \
  --since 2026-07-01 --until 2026-07-06

# Enable / disable an integration by id
gundi integrations enable  338225f3-91f9-4fe1-b013-353a229ce504
gundi integrations disable 338225f3-91f9-4fe1-b013-353a229ce504
```

Run `gundi --help` or `gundi integrations --help` for the full command list.

**Exit codes:** `0` success · `1` API or authentication error (a clean
`Error: …` message, no traceback) · `2` missing or invalid configuration.

### Named environments

Instead of exporting auth env vars each time, save named environments and switch
between them. Config lives in `~/.config/gundi/config.json` (mode 0600);
**secrets are never written** — only the OAuth tokens derived from them, cached
per environment under `~/.config/gundi/tokens/`.

```bash
# Add environments (connection config only — no secrets)
gundi env add prod --base-url https://api.gundi.example.com \
  --client-id my-client --issuer https://auth.example.com/realms/prod
gundi env add dev  --base-url https://api.dev.example.com \
  --client-id my-client --issuer https://auth.example.com/realms/dev --username me@example.com

gundi env use prod          # set the active environment
gundi env list              # '*' marks the active one
gundi env show prod

# Authenticate once; the token is cached and reused by later commands.
# The secret/password is read from env (OAUTH_CLIENT_SECRET / GUNDI_PASSWORD)
# or prompted (hidden) — and never stored.
gundi auth login                              # grant chosen by the env's config
gundi auth login --username me@example.com    # force the password grant
gundi auth status
gundi integrations list     # reuses the cached token; no re-auth

# Override the active environment per command:
gundi integrations list --profile dev
gundi auth logout
```

**Environment selection precedence:** `--profile` flag → `GUNDI_PROFILE` env var
→ stored active environment → raw `OAUTH_*` / `GUNDI_*` env vars (the original
behavior, used when no environments are configured).

**Token refresh:** password-grant environments refresh transparently using the
cached refresh token. Client-credentials environments (no refresh token) require
`gundi auth login` again once the access token expires.

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
