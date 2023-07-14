import logging
from datetime import datetime, timezone, timedelta
from httpx import (
    AsyncClient,
    AsyncHTTPTransport,
    Timeout,
)
from pydantic import parse_obj_as
from typing import List
from gundi_core.schemas import (
    OAuthToken,
)
from gundi_core.schemas.v2 import Connection, Route, Integration, GundiTrace
from . import settings, errors
from . import auth


logger = logging.getLogger(__name__)
logger.setLevel(settings.LOG_LEVEL)


class GundiClient:
    DEFAULT_CONNECT_TIMEOUT_SECONDS = 3.1
    DEFAULT_DATA_TIMEOUT_SECONDS = 20
    DEFAULT_CONNECTION_RETRIES = 5

    def __init__(self, **kwargs):
        # API settings
        self.gundi_version = "v2"
        self.base_url = kwargs.get("base_url", settings.GUNDI_API_BASE_URL)
        self.api_base_path = f"{self.base_url}/api/{self.gundi_version}"
        self.connections_endpoint = f"{self.api_base_path}/connections"
        self.integrations_endpoint = f"{self.api_base_path}/integrations"
        self.source_states_endpoint = f"{self.api_base_path}/sources/states"
        self.sources_endpoint = f"{self.api_base_path}/sources"
        self.routes_endpoint = f"{self.api_base_path}/routes"
        self.traces_endpoint = f"{self.api_base_path}/traces"

        # Authentication settings
        self.ssl_verify = kwargs.get("use_ssl", settings.GUNDI_API_SSL_VERIFY)
        self.client_id = kwargs.get("keycloak_client_id", settings.KEYCLOAK_CLIENT_ID)
        self.client_secret = kwargs.get("keycloak_client_secret", settings.KEYCLOAK_CLIENT_SECRET)
        self.oauth_token_url = kwargs.get("oauth_token_url", settings.OAUTH_TOKEN_URL)
        self.audience = kwargs.get("keycloak_audience", settings.KEYCLOAK_AUDIENCE)
        self.cached_token = None
        self.cached_token_expires_at = datetime.min.replace(tzinfo=timezone.utc)

        # Retries and timeouts settings
        self.max_retries = kwargs.get('max_http_retries', self.DEFAULT_CONNECTION_RETRIES)
        transport = AsyncHTTPTransport(retries=self.max_retries)
        connect_timeout = kwargs.get('connect_timeout', self.DEFAULT_CONNECT_TIMEOUT_SECONDS)
        data_timeout = kwargs.get('data_timeout', self.DEFAULT_DATA_TIMEOUT_SECONDS)
        timeout = Timeout(data_timeout, connect=connect_timeout, pool=connect_timeout)

        # Session
        self._session = AsyncClient(transport=transport, timeout=timeout, verify=self.ssl_verify)

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

        token = await auth.get_access_token(
            session=self._session,
            oauth_token_url=self.oauth_token_url,
            client_id=self.client_id,
            client_secret=self.client_secret,
            audience=self.audience
        )

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

    async def get_connection_details(self, integration_id):
        headers = await self.get_auth_header()
        url = f"{self.connections_endpoint}/{integration_id}/"
        response = await self._session.get(
            url,
            headers=headers,
        )
        # ToDo: Add custom exceptions to handle errors
        response.raise_for_status()
        data = response.json()
        return Connection.parse_obj(data)

    async def get_route_details(self, route_id):
        headers = await self.get_auth_header()
        url = f"{self.routes_endpoint}/{route_id}/"
        response = await self._session.get(
            url,
            headers=headers,
        )
        # ToDo: Add custom exceptions to handle errors
        response.raise_for_status()
        data = response.json()
        return Route.parse_obj(data)

    async def get_integration_details(self, integration_id):
        headers = await self.get_auth_header()
        url = f"{self.integrations_endpoint}/{integration_id}/"
        response = await self._session.get(
            url,
            headers=headers,
        )
        # ToDo: Add custom exceptions to handle errors
        response.raise_for_status()
        data = response.json()
        return Integration.parse_obj(data)

    async def get_traces(self, params: dict):
        headers = await self.get_auth_header()
        url = f"{self.traces_endpoint}/"
        response = await self._session.get(
            url,
            params=params,
            headers=headers,
        )
        # ToDo: Add custom exceptions to handle errors
        response.raise_for_status()
        data = response.json()['results']
        return parse_obj_as(List[GundiTrace], data)
