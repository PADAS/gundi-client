"""Tests for gundi_client_v2.transformations.apply_transformations."""

import logging
import uuid
from datetime import datetime, timezone

import pytest

from gundi_client_v2.transformations import apply_transformations
from gundi_core.schemas.v2 import (
    Event,
    Location,
    Observation,
    RouteConfiguration,
    StreamPrefixEnum,
    TextMessage,
)


PROVIDER_ID = "11111111-1111-1111-1111-111111111111"
DESTINATION_ID = "22222222-2222-2222-2222-222222222222"
OTHER_DESTINATION_ID = "33333333-3333-3333-3333-333333333333"


@pytest.fixture
def event():
    return Event(
        source_id=uuid.uuid4(),
        external_source_id="device-99",
        recorded_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        location=Location(lon=-122.0, lat=47.0),
        title="Sighting",
        event_type="initial_type",
        event_details={"species": "lion"},
    )


@pytest.fixture
def observation():
    return Observation(
        source_id=uuid.uuid4(),
        external_source_id="device-42",
        source_name="Collar 42",
        type="tracking-device",
        recorded_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        location=Location(lon=-122.0, lat=47.0),
    )


def _route_config(rules: dict) -> RouteConfiguration:
    return RouteConfiguration(
        id=uuid.uuid4(),
        name="Test route config",
        data={"field_mappings": rules},
    )


def test_no_route_configuration_returns_payload_unchanged(event):
    original_type = event.event_type
    result = apply_transformations(
        event,
        route_configuration=None,
        provider_id=PROVIDER_ID,
        destination_id=DESTINATION_ID,
    )
    assert result is event
    assert result.event_type == original_type


def test_empty_field_mappings_returns_payload_unchanged(event):
    config = _route_config({})
    apply_transformations(
        event,
        route_configuration=config,
        provider_id=PROVIDER_ID,
        destination_id=DESTINATION_ID,
    )
    assert event.event_type == "initial_type"


def test_value_map_translates_event_type_from_species(event):
    # The 7 real rules in production: read event_details.species, map values,
    # write to event_type.
    rules = {
        PROVIDER_ID: {
            StreamPrefixEnum.event.value: {
                DESTINATION_ID: {
                    "default": "other_camera_trap",
                    "provider_field": "event_details__species",
                    "destination_field": "event_type",
                    "map": {"lion": "lion_sighting", "leopard": "leopard_sighting"},
                }
            }
        }
    }
    apply_transformations(
        event,
        route_configuration=_route_config(rules),
        provider_id=PROVIDER_ID,
        destination_id=DESTINATION_ID,
    )
    assert event.event_type == "lion_sighting"


def test_value_map_falls_back_to_default_for_unmapped_value(event):
    event.event_details = {"species": "elephant"}
    rules = {
        PROVIDER_ID: {
            StreamPrefixEnum.event.value: {
                DESTINATION_ID: {
                    "default": "other_camera_trap",
                    "provider_field": "event_details__species",
                    "destination_field": "event_type",
                    "map": {"lion": "lion_sighting"},
                }
            }
        }
    }
    apply_transformations(
        event,
        route_configuration=_route_config(rules),
        provider_id=PROVIDER_ID,
        destination_id=DESTINATION_ID,
    )
    assert event.event_type == "other_camera_trap"


def test_default_only_rule_writes_default_to_target(event):
    rules = {
        PROVIDER_ID: {
            StreamPrefixEnum.event.value: {
                DESTINATION_ID: {
                    "default": "trailguard_rep",
                    "destination_field": "event_type",
                }
            }
        }
    }
    apply_transformations(
        event,
        route_configuration=_route_config(rules),
        provider_id=PROVIDER_ID,
        destination_id=DESTINATION_ID,
    )
    assert event.event_type == "trailguard_rep"


def test_missing_source_value_logs_and_does_not_mutate(event, caplog):
    event.event_details = {}
    rules = {
        PROVIDER_ID: {
            StreamPrefixEnum.event.value: {
                DESTINATION_ID: {
                    "default": "other_camera_trap",
                    "provider_field": "event_details__species",
                    "destination_field": "event_type",
                    "map": {"lion": "lion_sighting"},
                }
            }
        }
    }
    with caplog.at_level(logging.WARNING):
        apply_transformations(
            event,
            route_configuration=_route_config(rules),
            provider_id=PROVIDER_ID,
            destination_id=DESTINATION_ID,
        )
    assert event.event_type == "initial_type"  # untouched
    assert any("couldn't extract value" in r.message.lower() for r in caplog.records)


def test_unknown_target_field_logs_and_skips(observation, caplog):
    # This is exactly the 564 provider_key case — provider_key is not a field
    # on Observation, so the rule is skipped with a warning.
    rules = {
        PROVIDER_ID: {
            StreamPrefixEnum.observation.value: {
                DESTINATION_ID: {
                    "default": "telonics-collars",
                    "destination_field": "provider_key",
                }
            }
        }
    }
    with caplog.at_level(logging.WARNING):
        apply_transformations(
            observation,
            route_configuration=_route_config(rules),
            provider_id=PROVIDER_ID,
            destination_id=DESTINATION_ID,
        )
    assert not hasattr(observation, "provider_key")
    assert any("provider_key" in r.message and "skipping" in r.message for r in caplog.records)


def test_rule_for_different_destination_is_ignored(event):
    rules = {
        PROVIDER_ID: {
            StreamPrefixEnum.event.value: {
                OTHER_DESTINATION_ID: {
                    "default": "should_not_apply",
                    "destination_field": "event_type",
                }
            }
        }
    }
    apply_transformations(
        event,
        route_configuration=_route_config(rules),
        provider_id=PROVIDER_ID,
        destination_id=DESTINATION_ID,
    )
    assert event.event_type == "initial_type"


def test_rule_for_different_stream_type_is_ignored(event):
    rules = {
        PROVIDER_ID: {
            StreamPrefixEnum.observation.value: {
                DESTINATION_ID: {
                    "default": "should_not_apply",
                    "destination_field": "event_type",
                }
            }
        }
    }
    apply_transformations(
        event,
        route_configuration=_route_config(rules),
        provider_id=PROVIDER_ID,
        destination_id=DESTINATION_ID,
    )
    assert event.event_type == "initial_type"


def test_route_configuration_with_no_data_attribute_is_safe(event):
    config = RouteConfiguration(
        id=uuid.uuid4(),
        name="empty",
        data=None,
    )
    apply_transformations(
        event,
        route_configuration=config,
        provider_id=PROVIDER_ID,
        destination_id=DESTINATION_ID,
    )
    assert event.event_type == "initial_type"


def test_text_message_unknown_target_skipped(caplog):
    # txt-stream provider_key rules are the other 136 entries in the survey.
    message = TextMessage(
        source_id=uuid.uuid4(),
        external_source_id="device-tx",
        sender="555-0100",
        recipients=["dispatch@example.com"],
        text="Need help",
        created_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    rules = {
        PROVIDER_ID: {
            StreamPrefixEnum.text_message.value: {
                DESTINATION_ID: {
                    "default": "inreach-text",
                    "destination_field": "provider_key",
                }
            }
        }
    }
    with caplog.at_level(logging.WARNING):
        apply_transformations(
            message,
            route_configuration=_route_config(rules),
            provider_id=PROVIDER_ID,
            destination_id=DESTINATION_ID,
        )
    assert not hasattr(message, "provider_key")
    assert any("skipping" in r.message for r in caplog.records)
