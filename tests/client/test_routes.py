import httpx
import pytest
import respx
from gundi_core.schemas.v2 import Connection, Route, Integration


# ToDo: complete tests
# test_get_route_details
@pytest.mark.asyncio
async def test_get_route_details(
        auth_token_response, route_details, gundi_client_v2
):
    async with respx.mock(assert_all_called=False) as gundi_portal_mock:
        # Mock authentication
        gundi_portal_mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.CREATED,
            json=auth_token_response
        )
        # Mock configuration
        route_id = "775897f9-1ef2-4d10-9c6c-ea2663380c5b"
        route_details_url = f"{gundi_client_v2.routes_endpoint}/{route_id}/"
        gundi_portal_mock.get(route_details_url).respond(
            status_code=httpx.codes.OK,
            json=route_details
        )
        route = await gundi_client_v2.get_route_details(
            route_id=route_id
        )
        assert isinstance(route, Route)
        assert route == Route.parse_obj(route_details)
