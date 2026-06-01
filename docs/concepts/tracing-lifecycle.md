# Tracing and lifecycle

## How a payload moves through Gundi

Every observation, event, or message you send travels through a predictable
sequence of steps before it reaches a destination system. Understanding that
sequence makes it easier to diagnose problems and verify delivery.

1. **Ingestion.** A provider Integration delivers a payload to Gundi — via an
   inbound webhook, a scheduled pull action, or a direct call to
   `GundiDataSenderClient.post_observations()` / `post_events()` /
   `post_messages()`.

2. **ID assignment.** Gundi assigns the payload an internal identifier:
   `object_id`. This ID is stable and is the handle you use to look up Traces
   later.

3. **Connection lookup.** Gundi finds every Connection whose `provider` matches
   the Integration that delivered the payload.

4. **Route resolution.** For each matching Connection, Gundi evaluates its
   `routing_rules` to find the Routes that apply. If no rule matches, Gundi
   falls back to the Connection's `default_route` (if one is configured).

5. **Transform and forward.** For each (Route, destination) pair, Gundi applies
   the Route's `configuration` — typically a JQ filter — to the payload, then
   forwards the result to the destination Integration's API.

6. **Trace recording.** Gundi writes a `Trace` for every provider → destination
   edge in the flow, capturing the delivery outcome (success, error, duplicate
   suppression) and the `external_id` assigned by the destination.

## The Trace record

Each `Trace` corresponds to one payload crossing one provider → destination
edge. The fields below are the canonical set exposed by `gundi_core.schemas.v2.GundiTrace`.

| Field | Meaning |
|---|---|
| `object_id` | The Gundi-side ID of the source observation/event |
| `object_type` | Payload type discriminator |
| `related_to` | Parent object ID (e.g. for messages attached to an event) |
| `data_provider` | Provider Integration ID |
| `destination` | Destination Integration ID |
| `delivered_at` | When the payload reached the destination |
| `external_id` | The ID assigned by the destination (e.g. an EarthRanger event UUID) |
| `created_at` / `updated_at` | Trace timestamps |
| `last_update_delivered_at` | Time of the most recent successful update |
| `is_duplicate` | True if Gundi suppressed this as a duplicate |
| `has_error` | True if delivery errored |

You retrieve Traces with `GundiClient.get_traces(params={...})`.

## When to read traces

**Diagnosing a missing payload.** If a payload you sent never appeared at the
destination, pull its Traces and check `has_error`. If `has_error` is `True`,
the `Trace` record is your starting point for understanding what went wrong —
check the destination Integration's configuration and the Route's transformation
for the failing edge.

**Confirming delivery.** `delivered_at` tells you exactly when the destination
acknowledged receipt. If `delivered_at` is set and `has_error` is `False`, the
payload was delivered successfully. If `is_duplicate` is `True`, Gundi
suppressed it because an identical payload had already been delivered.

**Finding the destination's external ID.** Gundi stores the ID the destination
assigned to the forwarded payload in `external_id`. Use this when you need to
correlate a Gundi `object_id` with, say, an EarthRanger event UUID or a SMART
patrol ID for downstream operations.

**See also:**

- [Gundi data model](../concepts/data-model.md) — Integration, Connection, and
  Route vocabulary
- [Reading Traces](../reading-data/traces.md)
