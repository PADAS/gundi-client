"""Apply RouteConfiguration field_mappings to a generic Gundi payload.

Used by action runners that consume `GundiDelivery` envelopes from cdip-routing.
The function mirrors today's `FieldMappingRule` semantics in cdip-routing but
writes to top-level fields on the generic Gundi Pydantic model instead of to a
destination-shaped dict.

Rules whose `destination_field` does not exist on the payload (e.g., the 564
EarthRanger `provider_key` overrides) are logged and skipped — those values are
delivery metadata, not data, and are handled elsewhere.
"""

import logging
from typing import Any, Optional

from pydantic import BaseModel

from gundi_core.schemas.v2 import RouteConfiguration

logger = logging.getLogger(__name__)


def apply_transformations(
    payload: BaseModel,
    route_configuration: Optional[RouteConfiguration],
    *,
    provider_id: str,
    destination_id: str,
) -> BaseModel:
    """Apply transformations from route_configuration.field_mappings to payload.

    Mutates and returns the same payload instance. Rules are looked up by the
    triple (provider_id, stream_type, destination_id), where stream_type is read
    from `payload.observation_type`.

    Args:
        payload: A generic Gundi v2 schema instance (Observation, Event, etc.).
        route_configuration: The RouteConfiguration carried in the GundiDelivery
            envelope. May be None.
        provider_id: The inbound provider's UUID (from delivery.provider).
        destination_id: The runner's own destination integration UUID.

    Returns:
        The payload, mutated in place.
    """
    rule = _find_rule(
        route_configuration=route_configuration,
        payload=payload,
        provider_id=provider_id,
        destination_id=destination_id,
    )
    if rule:
        _apply_rule(payload=payload, rule=rule)
    return payload


def _find_rule(
    *,
    route_configuration: Optional[RouteConfiguration],
    payload: BaseModel,
    provider_id: str,
    destination_id: str,
) -> Optional[dict]:
    if route_configuration is None:
        return None
    data = getattr(route_configuration, "data", None) or {}
    field_mappings = data.get("field_mappings") or {}
    if not field_mappings:
        return None

    stream_type = getattr(payload, "observation_type", None)
    if not stream_type:
        return None

    rule = (
        field_mappings.get(str(provider_id), {})
        .get(str(stream_type), {})
        .get(str(destination_id), {})
    )
    return rule or None


def _apply_rule(*, payload: BaseModel, rule: dict) -> None:
    target = rule.get("destination_field")
    if not target:
        return

    if not hasattr(payload, target):
        # Target is not a field on this payload's model. Likely a destination-runner-
        # specific value such as EarthRanger's provider_key. Honored elsewhere.
        logger.warning(
            "apply_transformations: target '%s' is not a field on %s; skipping rule.",
            target,
            type(payload).__name__,
        )
        return

    source = rule.get("provider_field")
    default = rule.get("default")
    value_map = rule.get("map")

    if not source:
        if default is not None:
            setattr(payload, target, default)
        return

    source_value = _extract_value(payload=payload, source=source)
    if source_value is None:
        logger.warning(
            "apply_transformations: couldn't extract value for source '%s' on %s.",
            source,
            type(payload).__name__,
        )
        return

    if value_map:
        resolved = value_map.get(source_value, default)
    else:
        resolved = source_value

    setattr(payload, target, resolved)


def _extract_value(*, payload: Any, source: str) -> Any:
    """Walk a `__`-separated path on the payload (mix of attrs and dict keys)."""
    fields = source.lower().strip().split("__")
    value: Any = payload
    for field in fields:
        if value is None:
            return None
        if isinstance(value, dict):
            value = value.get(field)
        else:
            value = getattr(value, field, None)
    return value
