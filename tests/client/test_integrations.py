import json

import httpx
import pytest
import respx
from gundi_core.schemas.v2 import Connection, Route, Integration, IntegrationType

from gundi_client_v2 import errors

# ToDo: complete tests
# test_data_provider_details


@pytest.mark.asyncio
async def test_get_destination_integration_details(
    auth_token_response, destination_integration_details, gundi_client_v2
):
    async with respx.mock(assert_all_called=False) as gundi_portal_mock:
        # Mock authentication
        gundi_portal_mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.CREATED, json=auth_token_response
        )
        # Mock configuration
        integration_id = "228225f3-91f9-4fe1-b013-353a229ce505"
        integration_details_url = (
            f"{gundi_client_v2.integrations_endpoint}/{integration_id}/"
        )
        gundi_portal_mock.get(integration_details_url).respond(
            status_code=httpx.codes.OK, json=destination_integration_details
        )
        integration = await gundi_client_v2.get_integration_details(
            integration_id=integration_id
        )
        assert isinstance(integration, Integration)
        assert integration == Integration.parse_obj(destination_integration_details)


@pytest.mark.asyncio
async def test_get_integration_types_paginates(
    auth_token_response, destination_integration_details, gundi_client_v2
):
    type_payload = destination_integration_details["type"]  # full IntegrationType dict
    async with respx.mock(assert_all_called=False) as gundi_portal_mock:
        gundi_portal_mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        types_url = f"{gundi_client_v2.integrations_endpoint}/types/"
        page2 = f"{types_url}?cursor=2"
        gundi_portal_mock.get(page2).respond(
            status_code=httpx.codes.OK, json={"results": [type_payload], "next": None}
        )
        gundi_portal_mock.get(types_url).respond(
            status_code=httpx.codes.OK,
            json={"results": [type_payload], "next": page2},
        )

        results = [t async for t in gundi_client_v2.get_integration_types()]

    assert len(results) == 2  # two pages followed
    assert all(isinstance(t, IntegrationType) for t in results)
    assert results[0].value == "earth_ranger"


@pytest.mark.asyncio
async def test_get_activity_logs_paginates_and_yields_dicts(
    auth_token_response, gundi_client_v2
):
    log1 = {
        "id": "11111111-1111-1111-1111-111111111111",
        "created_at": "2026-06-12T09:00:00Z",
        "log_level": 20,
        "log_type": "event",
        "value": "integration_action_started",
        "title": "Action started",
        "integration": {"id": "abc", "name": "ER Site"},
    }
    log2 = {
        **log1,
        "id": "22222222-2222-2222-2222-222222222222",
        "title": "Action done",
    }
    async with respx.mock(assert_all_called=False) as gundi_portal_mock:
        gundi_portal_mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        logs_url = f"{gundi_client_v2.activity_logs_endpoint}/"
        page2 = f"{logs_url}?cursor=2"
        gundi_portal_mock.get(page2).respond(
            status_code=httpx.codes.OK, json={"results": [log2], "next": None}
        )
        gundi_portal_mock.get(logs_url).respond(
            status_code=httpx.codes.OK, json={"results": [log1], "next": page2}
        )

        results = [entry async for entry in gundi_client_v2.get_activity_logs()]

    assert [r["title"] for r in results] == ["Action started", "Action done"]
    assert all(isinstance(r, dict) for r in results)


@pytest.mark.asyncio
async def test_get_webhook_integration_details(
    auth_token_response, webhook_integration_details, gundi_client_v2
):
    async with respx.mock(assert_all_called=False) as gundi_portal_mock:
        # Mock authentication
        gundi_portal_mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.CREATED, json=auth_token_response
        )
        # Mock configuration
        integration_id = "817d3d4e-5dba-4792-8a30-a87603c5d201"
        integration_details_url = (
            f"{gundi_client_v2.integrations_endpoint}/{integration_id}/"
        )
        gundi_portal_mock.get(integration_details_url).respond(
            status_code=httpx.codes.OK, json=webhook_integration_details
        )
        integration = await gundi_client_v2.get_integration_details(
            integration_id=integration_id
        )
        assert isinstance(integration, Integration)
        assert integration == Integration.parse_obj(webhook_integration_details)


# cdip's write serializer renders type/owner/action as bare PK ids on the PATCH
# response — NOT the nested objects the Integration schema needs. update_integration
# must therefore re-read via GET (read serializer) rather than parse the PATCH body.
# These tests mock both calls with their realistic, differing shapes.
_WRITE_SERIALIZER_PATCH_RESPONSE = {
    "id": "338225f3-91f9-4fe1-b013-353a229ce504",
    "name": "Renamed Integration",
    "base_url": "https://gundi-load-testing.pamdas.org",
    "enabled": True,
    "type": "45c66a61-71e4-4664-a7f2-30d465f87aa6",  # bare PK, not nested
    "owner": "a1b2c3d4-0000-0000-0000-000000000000",  # bare PK, not nested
    "configurations": [
        {
            "id": "cfg-1",
            "integration": "338225f3-91f9-4fe1-b013-353a229ce504",
            "action": "43ec4163-2f40-43fc-af62-bca1db77c06b",
            "data": {},
        },  # action bare PK
    ],
}


@pytest.mark.asyncio
async def test_update_integration_patches_then_refetches(
    auth_token_response, destination_integration_details, gundi_client_v2
):
    integration_id = destination_integration_details["id"]
    patch_payload = {"name": "Renamed Integration"}
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        url = f"{gundi_client_v2.integrations_endpoint}/{integration_id}/"
        # PATCH returns the write-serializer shape (bare PK type/owner/action)...
        patch_integration = mock.patch(url).respond(
            status_code=httpx.codes.OK, json=_WRITE_SERIALIZER_PATCH_RESPONSE
        )
        # ...so the method re-reads the canonical (nested) representation via GET.
        get_integration = mock.get(url).respond(
            status_code=httpx.codes.OK, json=destination_integration_details
        )

        result = await gundi_client_v2.update_integration(
            integration_id, data=patch_payload
        )

        # Parses cleanly only because we re-fetch — parsing the PATCH body would raise.
        assert isinstance(result, Integration)
        assert result == Integration.parse_obj(destination_integration_details)
        assert patch_integration.call_count == 1
        assert get_integration.call_count == 1
        assert patch_integration.calls.last.request.method == "PATCH"
        sent = json.loads(patch_integration.calls.last.request.content.decode())
        assert sent == patch_payload


@pytest.mark.asyncio
async def test_update_integration_configuration_builds_configurations_payload(
    auth_token_response, destination_integration_details, gundi_client_v2
):
    import uuid

    integration_id = destination_integration_details["id"]
    configuration_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    new_data = {
        "event_type_to_tag": [
            {"event_type": "rhino_carcass", "tag_name": "Rhino Carcass"}
        ]
    }
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        url = f"{gundi_client_v2.integrations_endpoint}/{integration_id}/"
        patch_integration = mock.patch(url).respond(
            status_code=httpx.codes.OK, json=_WRITE_SERIALIZER_PATCH_RESPONSE
        )
        mock.get(url).respond(
            status_code=httpx.codes.OK, json=destination_integration_details
        )

        result = await gundi_client_v2.update_integration_configuration(
            integration_id, configuration_id, data=new_data
        )

        assert isinstance(result, Integration)
        assert patch_integration.calls.last.request.method == "PATCH"
        sent = json.loads(patch_integration.calls.last.request.content.decode())
        # The convenience wraps the single config update in the configurations list,
        # stringifying the UUID configuration_id.
        assert sent == {
            "configurations": [{"id": str(configuration_id), "data": new_data}]
        }


@pytest.mark.asyncio
async def test_update_integration_raises_gundi_api_error_on_400(
    auth_token_response, gundi_client_v2
):
    integration_id = "bogus-id"
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        mock.patch(
            f"{gundi_client_v2.integrations_endpoint}/{integration_id}/"
        ).respond(status_code=400, json={"detail": "bad patch"})

        with pytest.raises(errors.GundiAPIError) as exc:
            await gundi_client_v2.update_integration(integration_id, data={"name": ""})
        assert exc.value.status_code == 400
