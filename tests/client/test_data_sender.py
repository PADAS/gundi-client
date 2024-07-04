import httpx
import pytest
import respx


@pytest.mark.asyncio
async def test_post_observations(
    gundi_data_sender_client_v2, observation_payload, observations_created_response
):
    async with respx.mock(assert_all_called=False) as gundi_api_mock:
        # Mock API response
        observations_endpoint = f"{gundi_data_sender_client_v2.sensors_api_endpoint}/observations/"
        observations_api_mock = gundi_api_mock.post(observations_endpoint).respond(
            status_code=httpx.codes.CREATED,
            json=observations_created_response
        )

        response = await gundi_data_sender_client_v2.post_observations([observation_payload])
        assert response == observations_created_response
        assert observations_api_mock.called


@pytest.mark.asyncio
async def test_post_events(
    gundi_data_sender_client_v2, event_payload, events_created_response
):
    async with respx.mock(assert_all_called=False) as gundi_api_mock:
        # Mock API response
        events_endpoint = f"{gundi_data_sender_client_v2.sensors_api_endpoint}/events/"
        events_api_mock = gundi_api_mock.post(events_endpoint).respond(
            status_code=httpx.codes.CREATED,
            json=events_created_response
        )

        response = await gundi_data_sender_client_v2.post_events([event_payload])
        assert response == events_created_response
        assert events_api_mock.called


@pytest.mark.asyncio
async def test_post_event_attachment(
    gundi_data_sender_client_v2, event_attachment_payload, event_attachment_created_response
):
    async with respx.mock(assert_all_called=False) as gundi_api_mock:
        # Mock API response
        event_id = "dummy-123"
        events_endpoint = f"{gundi_data_sender_client_v2.sensors_api_endpoint}/events/{event_id}/attachments/"
        events_api_mock = gundi_api_mock.post(events_endpoint).respond(
            status_code=httpx.codes.OK,
            json=event_attachment_created_response
        )

        response = await gundi_data_sender_client_v2.post_event_attachments(event_id, [event_attachment_payload])
        assert response == event_attachment_created_response
        assert events_api_mock.called


@pytest.mark.asyncio
async def test_post_multiple_event_attachment(
    gundi_data_sender_client_v2,
    event_attachment_payload,
    another_event_attachment_payload,
    event_attachment_created_response
):
    async with respx.mock(assert_all_called=False) as gundi_api_mock:
        # Mock API response
        event_id = "dummy-123"
        events_endpoint = f"{gundi_data_sender_client_v2.sensors_api_endpoint}/events/{event_id}/attachments/"
        events_api_mock = gundi_api_mock.post(events_endpoint).respond(
            status_code=httpx.codes.OK,
            json=event_attachment_created_response
        )

        response = await gundi_data_sender_client_v2.post_event_attachments(
            event_id,
            [event_attachment_payload, another_event_attachment_payload]
        )
        assert response == event_attachment_created_response
        assert events_api_mock.called
