import httpx
import pytest
import respx

from gundi_client_v2 import errors


@pytest.mark.asyncio
async def test_get_raises_gundi_api_error_on_4xx(auth_token_response, gundi_client_v2):
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(gundi_client_v2.oauth_token_url).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        integration_id = "11115b4f-88cd-49c4-a723-0ddff1f580c4"
        url = f"{gundi_client_v2.integrations_endpoint}/{integration_id}/"
        mock.get(url).respond(status_code=404, json={"detail": "Not found"})
        with pytest.raises(errors.GundiAPIError) as exc:
            await gundi_client_v2.get_integration_details(integration_id)
        assert exc.value.status_code == 404
        assert "Not found" in exc.value.detail


@pytest.mark.asyncio
async def test_data_sender_post_raises_gundi_api_error(
    gundi_data_sender_client_v2, event_payload
):
    async with respx.mock as mock:
        url = f"{gundi_data_sender_client_v2.sensors_api_endpoint}/events/"
        mock.post(url).respond(status_code=500, json={"detail": "boom"})
        with pytest.raises(errors.GundiAPIError) as exc:
            await gundi_data_sender_client_v2.post_events(data=[event_payload])
        assert exc.value.status_code == 500
        assert "boom" in exc.value.detail


@pytest.mark.asyncio
async def test_data_sender_update_raises_gundi_api_error(gundi_data_sender_client_v2):
    async with respx.mock as mock:
        event_id = "abebe106-3c50-446b-9c98-0b9b503fc900"
        url = f"{gundi_data_sender_client_v2.sensors_api_endpoint}/events/{event_id}/"
        mock.patch(url).respond(status_code=400, json={"detail": "bad update"})
        with pytest.raises(errors.GundiAPIError) as exc:
            await gundi_data_sender_client_v2.update_event(
                event_id=event_id, data={"title": "x"}
            )
        assert exc.value.status_code == 400
        assert "bad update" in exc.value.detail
