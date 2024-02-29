import httpx
import pytest
import respx


@pytest.mark.asyncio
async def test_get_inbound_integration(
    auth_token_response, inbound_integration_config, gundi_client
):
    async with respx.mock(assert_all_called=False) as gundi_portal_mock:
        # Mock authentication
        gundi_portal_mock.post(gundi_client.oauth_token_url).respond(
            status_code=httpx.codes.CREATED,
            json=auth_token_response
        )
        # Mock configuration
        integration_id = "11115b4f-88cd-49c4-a723-0ddff1f580c4"
        inbound_url = gundi_client.portal_api_endpoint + f"/integrations/inbound/configurations/{integration_id}"
        gundi_portal_mock.get(inbound_url).respond(
            status_code=httpx.codes.OK,
            json=inbound_integration_config
        )
        response = await gundi_client.get_inbound_integration(integration_id=integration_id)
        assert response == inbound_integration_config


@pytest.mark.asyncio
async def test_get_outbound_integration(
    auth_token_response, gundi_client, outbound_integration_config
):
    # Mock authentication
    async with respx.mock(assert_all_called=False) as gundi_portal_mock:
        # Mock authentication
        gundi_portal_mock.post(gundi_client.oauth_token_url).respond(
            status_code=httpx.codes.CREATED,
            json=auth_token_response
        )
        # Mock configuration
        integration_id = "2222dc7e-73e2-4af3-93f5-a1cb322e5add"
        outbound_url = gundi_client.portal_api_endpoint + f"/integrations/outbound/configurations/{integration_id}"
        gundi_portal_mock.get(outbound_url).respond(
            status_code=httpx.codes.OK,
            json=outbound_integration_config
        )
        response = await gundi_client.get_outbound_integration(integration_id=integration_id)
        assert response == outbound_integration_config


@pytest.mark.asyncio
async def test_get_outbound_integrations_list(
    auth_token_response,
    gundi_client,
    outbound_integration_config_list,
):
    # Mock authentication
    async with respx.mock(assert_all_called=False) as gundi_portal_mock:
        # Mock authentication
        gundi_portal_mock.post(gundi_client.oauth_token_url).respond(
            status_code=httpx.codes.CREATED,
            json=auth_token_response
        )
        # Mock configuration
        outbound_list_url = gundi_client.portal_api_endpoint + f"/integrations/outbound/configurations"
        gundi_portal_mock.get(outbound_list_url).respond(
            status_code=httpx.codes.OK,
            json=outbound_integration_config_list
        )
        response = await gundi_client.get_outbound_integration_list()
        assert response == outbound_integration_config_list


@pytest.mark.asyncio
async def test_re_authenticate_on_login_redirection(
        auth_token_response, outbound_integration_config_list, gundi_client
):
    async with respx.mock(assert_all_called=True) as gundi_portal_mock:

        # Mock configurations response
        outbound_list_url = gundi_client.portal_api_endpoint + f"/integrations/outbound/configurations"
        gundi_portal_mock.get(outbound_list_url).side_effect = [
            httpx.Response(  # Fail the first time with a redirect to login
                status_code=302,
                headers={
                    "location": "https://cdip-auth.pamdas.org/auth/realms/some-id/protocol/openid-connect/auth?response_type=code&client_id=cdip-admin-portal"
                },
            ),
            httpx.Response(  # Succeed the second time
                status_code=httpx.codes.OK,
                json=outbound_integration_config_list
            ),
        ]
        # Mock token refresh response
        gundi_portal_mock.post(gundi_client.oauth_token_url).respond(
            status_code=httpx.codes.CREATED,
            json=auth_token_response
        )
        response = await gundi_client.get_outbound_integration_list()
        assert response == outbound_integration_config_list

