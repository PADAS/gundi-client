# Gundi data model

Gundi sits between **data providers** (devices, third-party APIs, telemetry
sources) and **destinations** (EarthRanger sites, SMART deployments, etc.).
Five resource types make up the platform:

```
Integration ──┐
              ├─► Connection ──► Route ──► Integration (destination)
Integration ──┘
```

## Integration

A registered third-party system that either **provides** data to Gundi or
**receives** data from it. Defined by an `IntegrationType` (e.g.
`er_traptagger`, `lotek`, `earthranger`) and an `IntegrationConfiguration`
that holds the system-specific settings (base URL, API key, etc.).

**You read these with:** [`get_integrations()`](../reading-data/integrations.md),
`get_integration_details(integration_id)`.

## Connection

A logical grouping of one or more provider Integrations that share a common
destination. A "TrapTagger camera trap network at Park X" might be a single
Connection containing several provider Integrations (each camera) routed to
one EarthRanger destination.

A Connection's primary fields:

- `provider` — the Integration that produces data
- `destinations` — list of Integrations that receive routed data
- `status` — `healthy`, `unhealthy`, `disabled`
- `routing_rules` — references to the Routes that direct the data

**You read these with:** [`get_connections()`](../reading-data/connections.md),
`get_connection_details(integration_id)`.

## Route

A rule that maps **provider** Integrations to **destination** Integrations,
with optional field-level transforms (often a JQ filter). Routes belong to an
**owner** Organization. A Connection's `routing_rules` are the Route IDs that
apply to it.

**You read these with:** `get_routes()`, `get_route_details(route_id)`,
`get_routes_for_connection(connection_id)`.
**You manage these with:** `create_route()`, `update_route()`, `delete_route()`.

## Observation, Event, Message

The three payload types Gundi forwards:

| Type | What it is | Sent with |
|---|---|---|
| **Observation** | A geolocated point (lat, lon, time, optional attributes) | `GundiDataSenderClient.post_observations` |
| **Event** | A discrete incident or record (type, time, location, attributes) | `GundiDataSenderClient.post_events` |
| **Message** | A text message (often paired with an Event or Observation) | `GundiDataSenderClient.post_messages` |

## Trace

A record of one payload's journey through Gundi: the source observation/event,
which Connection routed it, which destination(s) received it, and the
delivery outcome. Useful for diagnostics.

**You read these with:** `get_traces(params={...})`.

## How they fit together

A typical "provider → destination" flow:

1. A device pushes an Observation to Gundi via a provider Integration's
   webhook endpoint.
2. Gundi looks up the Connections containing that provider Integration.
3. For each matching Connection, Gundi consults its Routes to determine
   which destination Integrations should receive the data.
4. Gundi transforms the payload per the Route's `transformation_rules` if
   any, then forwards it to each destination.
5. A Trace is recorded for each provider → destination edge in the flow.
