# Payload types

## Three payload types

Gundi forwards three payload types: **Observations**, **Events**, and
**Messages**. Each maps to a different kind of real-world datum and a different
`GundiDataSenderClient` method. The [side-by-side table](#side-by-side-comparison)
at the bottom of this page summarises the key differences at a glance.

## Observation

An Observation is a **geolocated, time-stamped data point** produced
automatically by a sensor or telemetry device — a GPS collar fix, a camera-trap
detection, a stationary environmental sensor reading. Observations are the most
common payload type in Gundi integrations.

Common fields:

| Field | Notes |
|---|---|
| `source` | Identifier for the device or feed that produced the point |
| `type` | Payload sub-type; common values: `tracking-device`, `stationary-object`, `gps-radio-collar` |
| `recorded_at` | ISO-8601 timestamp when the device recorded the reading |
| `location.lat` / `location.lon` | WGS-84 decimal degrees (both required) |
| `additional` | Free-form dict for any extra sensor attributes |

Observations are always sent in batches (`List[dict]`), even when the batch
contains a single item.

**See also:** [Sending Observations](../sending-data/observations.md)

## Event

An Event is a **discrete, operator-meaningful incident** — a ranger sighting, a
poaching incident report, a system alarm. Events are typically created by a
human (or a rule engine acting on human-defined logic) rather than raw telemetry.

Common fields:

| Field | Notes |
|---|---|
| `event_type` | Domain-specific type string (e.g. `wildlife_sighting`, `fence_alarm`) |
| `recorded_at` | ISO-8601 timestamp when the incident occurred |
| `location.lat` / `location.lon` | WGS-84 decimal degrees (both required) |
| `event_details` | Dict of event-specific structured attributes |
| `title` | Short human-readable description |

Like Observations, Events are sent in batches.

**See also:** [Sending Events](../sending-data/events.md)

## Message

A Message is a **text annotation** — a comment, a dispatch note, a status
update. Messages are often attached to an Event to add context that doesn't fit
neatly into structured fields, but they can also stand alone.

Common fields:

Minimum fields:

| Field | Notes |
|---|---|
| `sender` | Identifier of the sending party |
| `recipients` | List of recipient identifiers (users, groups, or channels) |
| `text` | The message body |

Optional fields:

| Field | Notes |
|---|---|
| `event_id` | Links this message to an existing Event |
| `recorded_at` | ISO-8601 timestamp when the message was created |
| `location.latitude` / `location.longitude` | WGS-84 decimal degrees. **Note:** Messages use the long form `latitude`/`longitude`, unlike Observations and Events which use `lat`/`lon`. |

Messages are sent in batches.

**See also:** [Sending Messages and Attachments](../sending-data/messages-attachments.md)

## Side-by-side comparison

| Aspect | Observation | Event | Message |
|---|---|---|---|
| Has a location | Yes (required) | Yes (required) | Optional |
| Has a time | `recorded_at` | `recorded_at` | `recorded_at` (optional) |
| Sent in batches | Yes (`List[dict]`) | Yes (`List[dict]`) | Yes (`List[dict]`) |
| Common source | Telemetry / sensors | Operator-entered incidents | Comms / context |

## What gets routed where

All three payload types flow through the same routing machinery. When Gundi
receives any payload it:

1. Looks up the Connections that include the provider Integration.
2. Evaluates the matching Routes for each Connection.
3. Applies any field-level transformation defined in the Route's `configuration`
   (often a JQ filter) to the payload.
4. Forwards the transformed payload to each destination Integration.

No payload type is treated as special by the router — a Route's `configuration`
applies equally to Observations, Events, and Messages. The payload type
determines only which `GundiDataSenderClient` method you call on the sending
side and which schema the destination expects on the receiving side.

**See also:**

- [Gundi data model](../concepts/data-model.md) — Integration, Connection, and
  Route vocabulary
- [Sending Observations](../sending-data/observations.md)
- [Sending Events](../sending-data/events.md)
- [Sending Messages and Attachments](../sending-data/messages-attachments.md)
