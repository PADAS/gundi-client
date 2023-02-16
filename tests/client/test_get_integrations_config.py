import pytest
import aiohttp
import re


@pytest.mark.asyncio
async def test_get_inbound_integration(
    mock_aioresponse, gundi_client, auth_token_response, inbound_integration_config
):
    # Mock authentication
    regex = r".*/protocol/openid-connect/token$"
    auth_pattern = re.compile(regex)
    mock_aioresponse.post(auth_pattern, payload=auth_token_response)
    # Mock configuration
    integration_id = "11115b4f-88cd-49c4-a723-0ddff1f580c4"
    regex = r".*/api/v1.0/integrations/inbound/configurations*"
    integration_pattern = re.compile(regex)
    mock_aioresponse.get(integration_pattern, payload=inbound_integration_config)
    async with aiohttp.ClientSession() as session:
        response = await gundi_client.get_inbound_integration(
            session=session, integration_id=integration_id
        )
    assert response == inbound_integration_config


@pytest.mark.asyncio
async def test_get_outbound_integration(
    mock_aioresponse, gundi_client, auth_token_response, outbound_integration_config
):
    # Mock authentication
    regex = r".*/protocol/openid-connect/token$"
    auth_pattern = re.compile(regex)
    mock_aioresponse.post(auth_pattern, payload=auth_token_response)
    # Mock configuration
    integration_id = "2222dc7e-73e2-4af3-93f5-a1cb322e5add"
    regex = r".*/api/v1.0/integrations/outbound/configurations*"
    integration_pattern = re.compile(regex)
    mock_aioresponse.get(integration_pattern, payload=outbound_integration_config)
    async with aiohttp.ClientSession() as session:
        response = await gundi_client.get_outbound_integration(
            session=session, integration_id=integration_id
        )
    assert response == outbound_integration_config


@pytest.mark.asyncio
async def test_get_outbound_integrations_list(
    mock_aioresponse,
    gundi_client,
    auth_token_response,
    outbound_integration_config_list,
):
    # Mock authentication
    regex = r".*/protocol/openid-connect/token$"
    auth_pattern = re.compile(regex)
    mock_aioresponse.post(auth_pattern, payload=auth_token_response)
    # Mock configuration
    regex = r".*/api/v1.0/integrations/outbound/configurations$"
    integration_pattern = re.compile(regex)
    mock_aioresponse.get(integration_pattern, payload=outbound_integration_config_list)
    async with aiohttp.ClientSession() as session:
        response = await gundi_client.get_outbound_integration_list(session=session)
    assert response == outbound_integration_config_list
