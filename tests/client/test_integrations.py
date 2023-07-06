import httpx
import pytest
import respx
from gundi_core.schemas.v2 import Connection, Route, Integration

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

