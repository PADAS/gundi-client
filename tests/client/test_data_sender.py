import httpx
import pytest
import respx


@pytest.mark.asyncio
async def test_post_observations(
    gundi_data_sender_client_v2, observation_request
):
    async with respx.mock(assert_all_called=False) as gundi_api_mock:
        # Mock authentication
        gundi_api_mock.post(
            gundi_data_sender_client_v2.sensors_api_endpoint + "/observations/"
        ).respond(
            status_code=httpx.codes.CREATED,
            json=[]
        )

        response = await gundi_data_sender_client_v2.post_observations([observation_request])

    assert response is not None
