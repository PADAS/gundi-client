import json

import httpx
import pytest
import respx
from gundi_core.schemas.v2 import Connection, Route, Integration

from gundi_client_v2 import errors


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


@pytest.mark.asyncio
async def test_get_routes_parses_results_envelope(auth_token_response, route_details, gundi_client_v2):
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(status_code=httpx.codes.OK, json=auth_token_response)
        mock.get(f"{gundi_client_v2.routes_endpoint}/").respond(
            status_code=httpx.codes.OK, json={"results": [route_details], "next": None}
        )
        routes = await gundi_client_v2.get_routes()
        assert len(routes) == 1
        assert isinstance(routes[0], Route)


@pytest.mark.asyncio
async def test_get_routes_parses_bare_list(auth_token_response, route_details, gundi_client_v2):
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(status_code=httpx.codes.OK, json=auth_token_response)
        mock.get(f"{gundi_client_v2.routes_endpoint}/").respond(
            status_code=httpx.codes.OK, json=[route_details]
        )
        routes = await gundi_client_v2.get_routes()
        assert len(routes) == 1
        assert isinstance(routes[0], Route)


@pytest.mark.asyncio
async def test_get_routes_for_connection_filters_by_provider(auth_token_response, route_details, gundi_client_v2):
    connection_id = "ddd0946d-15b0-4308-b93d-e0470b6d33b6"
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(status_code=httpx.codes.OK, json=auth_token_response)
        route = mock.get(f"{gundi_client_v2.routes_endpoint}/").respond(
            status_code=httpx.codes.OK, json={"results": [route_details], "next": None}
        )
        await gundi_client_v2.get_routes_for_connection(connection_id)
        # The request URL must include ?provider=<connection_id>
        assert route.call_count == 1
        request_url = str(route.calls.last.request.url)
        assert f"provider={connection_id}" in request_url


@pytest.mark.asyncio
async def test_create_route_posts_with_data(auth_token_response, route_details, gundi_client_v2):
    payload = {
        "name": "TrapTagger → ER (events)",
        "owner": "e2d1b0fc-69fe-408b-afc5-7f54872730c0",
        "data_providers": ["ddd0946d-15b0-4308-b93d-e0470b6d33b6"],
        "destinations": ["338225f3-91f9-4fe1-b013-353a229ce504"],
    }
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(status_code=httpx.codes.OK, json=auth_token_response)
        post_route = mock.post(f"{gundi_client_v2.routes_endpoint}/").respond(
            status_code=httpx.codes.CREATED, json=route_details
        )
        result = await gundi_client_v2.create_route(data=payload)
        assert isinstance(result, Route)
        assert post_route.call_count == 1
        sent = json.loads(post_route.calls.last.request.content.decode())
        assert sent == payload


@pytest.mark.asyncio
async def test_create_route_raises_gundi_api_error_on_400(auth_token_response, gundi_client_v2):
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(status_code=httpx.codes.OK, json=auth_token_response)
        mock.post(f"{gundi_client_v2.routes_endpoint}/").respond(
            status_code=400, json={"detail": "bad route"}
        )
        with pytest.raises(errors.GundiAPIError) as exc:
            await gundi_client_v2.create_route(data={"name": "broken"})
        assert exc.value.status_code == 400
        assert "bad route" in exc.value.detail


@pytest.mark.asyncio
async def test_update_route_patches_with_partial_data(auth_token_response, route_details, gundi_client_v2):
    route_id = route_details["id"]
    patch_payload = {"name": "Renamed"}
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(status_code=httpx.codes.OK, json=auth_token_response)
        patch_route = mock.patch(f"{gundi_client_v2.routes_endpoint}/{route_id}/").respond(
            status_code=httpx.codes.OK, json=route_details
        )
        result = await gundi_client_v2.update_route(route_id, data=patch_payload)
        assert isinstance(result, Route)
        assert patch_route.call_count == 1
        # Confirm verb is PATCH and body matches the partial dict
        assert patch_route.calls.last.request.method == "PATCH"
        sent = json.loads(patch_route.calls.last.request.content.decode())
        assert sent == patch_payload


@pytest.mark.asyncio
async def test_update_route_raises_gundi_api_error_on_400(auth_token_response, gundi_client_v2):
    route_id = "bogus-id"
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(status_code=httpx.codes.OK, json=auth_token_response)
        mock.patch(f"{gundi_client_v2.routes_endpoint}/{route_id}/").respond(
            status_code=400, json={"detail": "bad patch"}
        )
        with pytest.raises(errors.GundiAPIError) as exc:
            await gundi_client_v2.update_route(route_id, data={"name": ""})
        assert exc.value.status_code == 400
        assert "bad patch" in exc.value.detail


@pytest.mark.asyncio
async def test_delete_route_issues_delete_and_returns_none(auth_token_response, route_details, gundi_client_v2):
    route_id = route_details["id"]
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(status_code=httpx.codes.OK, json=auth_token_response)
        delete_route = mock.delete(f"{gundi_client_v2.routes_endpoint}/{route_id}/").respond(
            status_code=204
        )
        result = await gundi_client_v2.delete_route(route_id)
        assert result is None
        assert delete_route.call_count == 1
        assert delete_route.calls.last.request.method == "DELETE"


@pytest.mark.asyncio
async def test_delete_route_raises_on_404(auth_token_response, gundi_client_v2):
    route_id = "nonexistent-uuid"
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(status_code=httpx.codes.OK, json=auth_token_response)
        mock.delete(f"{gundi_client_v2.routes_endpoint}/{route_id}/").respond(
            status_code=404, json={"detail": "Not found"}
        )
        with pytest.raises(errors.GundiAPIError) as exc:
            await gundi_client_v2.delete_route(route_id)
        assert exc.value.status_code == 404
        assert "Not found" in exc.value.detail
