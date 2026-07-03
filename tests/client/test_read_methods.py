import httpx
import pytest
import respx
from gundi_core.schemas.v2 import Connection, Integration


def _integration(idx):
    return {
        "id": f"338225f3-91f9-4fe1-b013-35322900000{idx}",
        "name": f"Integration {idx}",
        "base_url": "https://example.org",
        "enabled": True,
        "type": {
            "id": "45c66a61-71e4-4664-a7f2-30d465f87aa6",
            "name": "EarthRanger",
            "value": "earth_ranger",
            "description": "",
            "actions": [],
        },
        "owner": {
            "id": "e2d1b0fc-69fe-408b-afc5-7f54872730c0",
            "name": "Org",
            "description": "",
        },
        "configurations": [],
        "additional": {},
        "default_route": None,
        "status": "healthy",
    }


@pytest.mark.asyncio
async def test_get_connections_parses_bare_list(
    auth_token_response, connection_details, gundi_client_v2
):
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        mock.get(f"{gundi_client_v2.connections_endpoint}/").respond(
            status_code=httpx.codes.OK, json=[connection_details]
        )
        result = await gundi_client_v2.get_connections()
        assert len(result) == 1
        assert isinstance(result[0], Connection)


@pytest.mark.asyncio
async def test_get_connections_parses_results_envelope(
    auth_token_response, connection_details, gundi_client_v2
):
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        mock.get(f"{gundi_client_v2.connections_endpoint}/").respond(
            status_code=httpx.codes.OK,
            json={"results": [connection_details], "next": None},
        )
        result = await gundi_client_v2.get_connections()
        assert len(result) == 1
        assert isinstance(result[0], Connection)


@pytest.mark.asyncio
async def test_get_integrations_follows_pagination(
    auth_token_response, gundi_client_v2
):
    page2 = f"{gundi_client_v2.integrations_endpoint}/?cursor=abc"
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        # Register the more-specific page2 route first so respx matches it before the base route
        mock.get(page2).respond(
            status_code=httpx.codes.OK,
            json={"results": [_integration(2)], "next": None},
        )
        mock.get(f"{gundi_client_v2.integrations_endpoint}/").respond(
            status_code=httpx.codes.OK,
            json={"results": [_integration(1)], "next": page2},
        )
        collected = [i async for i in gundi_client_v2.get_integrations()]
        assert [i.name for i in collected] == ["Integration 1", "Integration 2"]
        assert all(isinstance(i, Integration) for i in collected)


@pytest.mark.asyncio
async def test_get_integrations_single_page_list(auth_token_response, gundi_client_v2):
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        mock.get(f"{gundi_client_v2.integrations_endpoint}/").respond(
            status_code=httpx.codes.OK, json=[_integration(1)]
        )
        collected = [i async for i in gundi_client_v2.get_integrations()]
        assert len(collected) == 1


@pytest.mark.asyncio
async def test_get_integrations_single_object_response(
    auth_token_response, gundi_client_v2
):
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        mock.get(f"{gundi_client_v2.integrations_endpoint}/").respond(
            status_code=httpx.codes.OK, json=_integration(1)
        )
        collected = [i async for i in gundi_client_v2.get_integrations()]
        assert len(collected) == 1
        assert isinstance(collected[0], Integration)


@pytest.mark.asyncio
async def test_get_integrations_empty_results(auth_token_response, gundi_client_v2):
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        mock.get(f"{gundi_client_v2.integrations_endpoint}/").respond(
            status_code=httpx.codes.OK, json={"results": [], "next": None}
        )
        collected = [i async for i in gundi_client_v2.get_integrations()]
        assert collected == []
