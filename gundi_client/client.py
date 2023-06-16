import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from uuid import UUID
from pydantic import parse_obj_as
from . import settings
from gundi_core.schemas import (
    IntegrationInformation,
    OAuthToken,
    TIntegrationInformation,
    DeviceState,
    OutboundConfiguration,
)
from httpx import (
    AsyncClient,
    AsyncHTTPTransport,
    RequestError,
    Timeout,
    TimeoutException,
    HTTPStatusError
)

logger = logging.getLogger(__name__)
logger.setLevel(settings.LOG_LEVEL)


class PortalApi:

    DEFAULT_CONNECT_TIMEOUT_SECONDS = 3.1
    DEFAULT_DATA_TIMEOUT_SECONDS = 20
    DEFAULT_CONNECTION_RETRIES = 5

    def __init__(self, **kwargs):
        self.client_id = kwargs.get("KEYCLOAK_CLIENT_ID", settings.KEYCLOAK_CLIENT_ID)
        self.client_secret = kwargs.get("KEYCLOAK_CLIENT_SECRET", settings.KEYCLOAK_CLIENT_SECRET)
        self.integrations_endpoint = (
            f'{kwargs.get("PORTAL_API_ENDPOINT", settings.PORTAL_API_ENDPOINT)}/integrations/inbound/configurations'
        )
        self.device_states_endpoint = f'{kwargs.get("PORTAL_API_ENDPOINT", settings.PORTAL_API_ENDPOINT)}/devices/states'
        self.devices_endpoint = f'{kwargs.get("PORTAL_API_ENDPOINT", settings.PORTAL_API_ENDPOINT)}/devices'

        self.oauth_token_url = kwargs.get("OAUTH_TOKEN_URL", settings.OAUTH_TOKEN_URL)
        self.audience = kwargs.get("KEYCLOAK_AUDIENCE", settings.KEYCLOAK_AUDIENCE)
        self.portal_api_endpoint = kwargs.get("PORTAL_API_ENDPOINT", settings.PORTAL_API_ENDPOINT)

        self.cached_token = None
        self.cached_token_expires_at = datetime.min.replace(tzinfo=timezone.utc)

        self.max_retries = kwargs.get('max_http_retries', self.DEFAULT_CONNECTION_RETRIES)
        transport = AsyncHTTPTransport(retries=self.max_retries)

        connect_timeout = kwargs.get('connect_timeout', self.DEFAULT_CONNECT_TIMEOUT_SECONDS)
        data_timeout = kwargs.get('data_timeout', self.DEFAULT_DATA_TIMEOUT_SECONDS)
        timeout = Timeout(data_timeout, connect=connect_timeout, pool=connect_timeout)

        self._session = AsyncClient(transport=transport, timeout=timeout, verify=settings.CDIP_ADMIN_SSL_VERIFY)

    async def close(self):
        await self._session.aclose()

    # Support using this client as an async context manager.
    async def __aenter__(self):
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self._session.__aexit__()

    async def get_access_token(self) -> OAuthToken:
        if self.cached_token and self.cached_token_expires_at > datetime.now(
            tz=timezone.utc
        ):
            return self.cached_token

        logger.debug(
            f"get_access_token from {self.oauth_token_url} using client_id: {self.client_id}"
        )
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "audience": self.audience,
            "grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
            "scope": "openid",
        }

        response = await self._session.post(
            self.oauth_token_url, data=payload
        )

        response.raise_for_status()
        token = response.json()
        token = OAuthToken.parse_obj(token)
        self.cached_token_expires_at = datetime.now(tz=timezone.utc) + timedelta(
            seconds=token.expires_in - 15
        )  # fudge factor
        self.cached_token = token
        return token

    async def get_auth_header(self) -> dict:
        token_object = await self.get_access_token()
        return {
            "authorization": f"{token_object.token_type} {token_object.access_token}"
        }

    async def get_destinations(
        self, *args, integration_id: str = None, device_id: str = None
    ):
        headers = await self.get_auth_header()

        url = f"{self.portal_api_endpoint}/integrations/outbound/configurations"
        response = await self._session.get(
            url,
            params={"inbound_id": integration_id, "device_id": device_id},
            headers=headers,
        )

        response.raise_for_status()
        data = response.json()

        return [OutboundConfiguration.parse_obj(item) for item in data]

    async def get_authorized_integrations(
        self,
        t_int_info: TIntegrationInformation = IntegrationInformation,
    ) -> List[IntegrationInformation]:
        logger.debug(f"get_authorized_integrations for : {settings.KEYCLOAK_CLIENT_ID}")
        headers = await self.get_auth_header()

        logger.debug(f"url: {self.integrations_endpoint}")
        response = await self._session.get(
            url=self.integrations_endpoint,
            headers=headers,
        )
        response.raise_for_status()
        json_response = response.json()

        if isinstance(json_response, dict):
            json_response = [json_response]

        logger.debug(
            f"Got {len(json_response)} integrations for {settings.KEYCLOAK_CLIENT_ID}"
        )
        return [t_int_info.parse_obj(r) for r in json_response]

    async def update_state(
        self, integration_info: IntegrationInformation
    ):
        headers = await self.get_auth_header()

        response = await self._session.put(
            url=f"{self.integrations_endpoint}/{integration_info.id}",
            headers=headers,
            json=dict(state=integration_info.state),
        )
        logger.info(f"update integration state resp: {response.json()}")
        response.raise_for_status()

        return await self.update_states_with_dict(
            integration_info.id, integration_info.device_states
        )

    async def fetch_device_states(self, inbound_id: UUID):
        try:
            headers = await self.get_auth_header()

            # This ought to be quick so just do it straight away.
            response = await self._session.get(
                url=f"{self.device_states_endpoint}/",
                params={"inbound_config_id": str(inbound_id)},
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()
        except (RequestError, TimeoutException, HTTPStatusError):
            logger.exception(f"Failed to get devices for iic: {inbound_id}")
        else:
            states_received = parse_obj_as(List[DeviceState], result)
            # todo: cleanup after all functions have their device state migrated over
            states_asdict = {}
            for s in states_received:
                if isinstance(s.state, dict) and "value" in s.state:
                    states_asdict[s.device_external_id] = s.state.get("value")
                else:
                    states_asdict[s.device_external_id] = s.state
            return states_asdict
            # return {s.device_external_id: s.state for s in states_received}

    async def ensure_device(
        self, inbound_id: UUID, external_id: str
    ):
        try:
            # Post device ID and Integration ID combination to ensure it exists
            # in the Portal's database and is also in the Integration's default
            # device group.
            headers = await self.get_auth_header()
            payload = {"external_id": external_id, "inbound_configuration": inbound_id}
            response = await self._session.post(
                url=self.devices_endpoint,
                json=payload,
                headers=headers,
            )
            # print(resp)
            response.raise_for_status()
            resp = response.json()
            return resp
        except RequestError:
            logger.exception(
                "Failed to post device to portal (request failed).",
                extra={**payload},
            )
        except TimeoutException:
            logger.exception(
                "Failed to post device to portal (timeout).",
                extra={**payload},
            )
        except HTTPStatusError:
            logger.exception(
                "Failed to post device to portal (HTTP returned error).",
                extra={**payload},
            )

        return None

    async def update_states_with_dict(
        self, inbound_id: UUID, states_dict: Dict[str, Any]
    ):
        headers = await self.get_auth_header()
        response = await self._session.post(
            url=f"{self.device_states_endpoint}/update/{inbound_id}",
            headers=headers,
            json=states_dict,
        )
        response.raise_for_status()
        text = response.json()
        logger.info(f"update device_states resp: {response.json()}")
        return text

    async def _get(self, url: str, params=None):
        headers = await self.get_auth_header()
        response = await self._session.get(
            url=url,
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def get_bridge_integration(self, bridge_id: str):
        return await self._get(
            url=f"{self.portal_api_endpoint}/integrations/bridges/{bridge_id}",
        )

    async def get_inbound_integration(
        self, integration_id: str
    ):
        return await self._get(
            url=f"{self.portal_api_endpoint}/integrations/inbound/configurations/{integration_id}",
        )

    async def get_outbound_integration(
        self, integration_id: str
    ):
        return await self._get(
            url=f"{self.portal_api_endpoint}/integrations/outbound/configurations/{integration_id}",
        )

    async def get_outbound_integration_list(
        self, **query_params
    ):
        return await self._get(
            url=f"{self.portal_api_endpoint}/integrations/outbound/configurations",
            params=query_params,
        )
