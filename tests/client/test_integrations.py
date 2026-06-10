import json

import httpx
import pytest
import respx
from gundi_core.schemas.v2 import Connection, Route, Integration

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
            status_code=httpx.codes.CREATED,
            json=auth_token_response
        )
        # Mock configuration
        integration_id = "228225f3-91f9-4fe1-b013-353a229ce505"
        integration_details_url = f"{gundi_client_v2.integrations_endpoint}/{integration_id}/"
        gundi_portal_mock.get(integration_details_url).respond(
            status_code=httpx.codes.OK,
            json=destination_integration_details
        )
        integration = await gundi_client_v2.get_integration_details(
            integration_id=integration_id
        )
        assert isinstance(integration, Integration)
        assert integration == Integration.parse_obj(destination_integration_details)


@pytest.mark.asyncio
async def test_get_webhook_integration_details(
    auth_token_response, webhook_integration_details, gundi_client_v2
):
    async with respx.mock(assert_all_called=False) as gundi_portal_mock:
        # Mock authentication
        gundi_portal_mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.CREATED,
            json=auth_token_response
        )
        # Mock configuration
        integration_id = "817d3d4e-5dba-4792-8a30-a87603c5d201"
        integration_details_url = f"{gundi_client_v2.integrations_endpoint}/{integration_id}/"
        gundi_portal_mock.get(integration_details_url).respond(
            status_code=httpx.codes.OK,
            json=webhook_integration_details
        )
        integration = await gundi_client_v2.get_integration_details(
            integration_id=integration_id
        )
        assert isinstance(integration, Integration)
        assert integration == Integration.parse_obj(webhook_integration_details)


@pytest.mark.asyncio
async def test_update_integration_patches_with_partial_data(
    auth_token_response, destination_integration_details, gundi_client_v2
):
    integration_id = destination_integration_details["id"]
    patch_payload = {"name": "Renamed Integration"}
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        patch_integration = mock.patch(
            f"{gundi_client_v2.integrations_endpoint}/{integration_id}/"
        ).respond(status_code=httpx.codes.OK, json=destination_integration_details)

        result = await gundi_client_v2.update_integration(integration_id, data=patch_payload)

        assert isinstance(result, Integration)
        assert patch_integration.call_count == 1
        assert patch_integration.calls.last.request.method == "PATCH"
        sent = json.loads(patch_integration.calls.last.request.content.decode())
        assert sent == patch_payload


@pytest.mark.asyncio
async def test_update_integration_configuration_builds_configurations_payload(
    auth_token_response, destination_integration_details, gundi_client_v2
):
    integration_id = destination_integration_details["id"]
    configuration_id = "11111111-1111-1111-1111-111111111111"
    new_data = {"event_type_to_tag": [{"event_type": "rhino_carcass", "tag_name": "Rhino Carcass"}]}
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        patch_integration = mock.patch(
            f"{gundi_client_v2.integrations_endpoint}/{integration_id}/"
        ).respond(status_code=httpx.codes.OK, json=destination_integration_details)

        result = await gundi_client_v2.update_integration_configuration(
            integration_id, configuration_id, data=new_data
        )

        assert isinstance(result, Integration)
        assert patch_integration.calls.last.request.method == "PATCH"
        sent = json.loads(patch_integration.calls.last.request.content.decode())
        # The convenience wraps the single config update in the configurations list
        assert sent == {
            "configurations": [{"id": configuration_id, "data": new_data}]
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

