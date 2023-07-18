import httpx
import pytest
import respx
from pydantic import parse_obj_as
from typing import List
from gundi_core.schemas.v2 import GundiTrace


@pytest.mark.asyncio
async def test_get_traces_list(
        auth_token_response, gundi_client_v2,
        traces_list_response, trace_object_id, trace_destination_id
):
    async with respx.mock(assert_all_called=False) as gundi_portal_mock:
        # Mock authentication
        gundi_portal_mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.CREATED,
            json=auth_token_response
        )
        # Mock configuration
        traces_list_url = f"{gundi_client_v2.traces_endpoint}/"
        gundi_portal_mock.get(traces_list_url).respond(
            status_code=httpx.codes.OK,
            json=traces_list_response
        )
        traces = await gundi_client_v2.get_traces(
            params={  # Filters
                "object_id": trace_object_id,
                "destination_id": trace_destination_id,
            }
        )
        assert traces
        assert traces == parse_obj_as(List[GundiTrace], traces_list_response.get("results"))
