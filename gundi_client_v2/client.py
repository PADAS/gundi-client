import logging
import json
import httpx

from datetime import datetime, timezone, timedelta
from httpx import (
    AsyncClient,
    AsyncHTTPTransport,
    Timeout,
)
from pydantic import parse_obj_as
from typing import AsyncGenerator, List
from gundi_core.schemas import (
    OAuthToken,
)
from gundi_core.schemas.v2 import Connection, Route, Integration, GundiTrace, IntegrationType
from . import settings, errors
from . import auth


logger = logging.getLogger(__name__)
logger.setLevel(settings.LOG_LEVEL)


class GundiDataSenderClient:
    def __init__(self, integration_api_key: str = None, **kwargs):
        self.gundi_version = "v2"
        self.sensors_api_endpoint = (
            f"{kwargs.get('sensors_api_base_url', settings.SENSORS_API_BASE_URL)}/{self.gundi_version}"
        )
        self._api_key = integration_api_key

    async def post_observations(self, data: List[dict]) -> dict:
        return await self._post_data(data=data, endpoint="observations")

    async def post_events(self, data: List[dict]) -> dict:
        return await self._post_data(data=data, endpoint="events")

    async def post_messages(self, data: List[dict]) -> dict:
        return await self._post_data(data=data, endpoint="messages")

    async def update_event(self, event_id: str, data: dict) -> dict:
        return await self._update_data(data=data, endpoint=f"events/{event_id}")

    async def post_event_attachments(self, event_id: str, attachments: List[tuple]) -> dict:
        return await self._post_data(attachments=attachments, endpoint=f"events/{event_id}/attachments")

    async def _post_data(self, data: List[dict] = None, endpoint: str = None, attachments: List[tuple] = None) -> dict:
        apikey = self._api_key

        logger.info(
            f' -- Posting to routing services --',
            extra={"integration_api_key": apikey}
        )

        url = f"{self.sensors_api_endpoint}/{endpoint}/"

        request = dict(
            url=url,
            headers={"apikey": apikey}
        )

        if data:
            clean_batch = [json.loads(json.dumps(r, default=str)) for r in data]
            request["json"] = clean_batch

        if attachments:
            request["files"] = [
                ('file', (filename, image_binary)) for filename, image_binary in attachments
            ]

        logger.debug(
            f" -- sending {endpoint}. --",
            extra={
                "length": len(data or attachments),
                "api": url,
            },
        )

        async with httpx.AsyncClient(timeout=120) as session:
            client_response = await session.post(**request)

        errors.raise_for_status(client_response)

        return client_response.json()

    async def _update_data(self, data: dict = None, endpoint: str = None) -> dict:
        apikey = self._api_key

        logger.info(
            f' -- Updating data... --',
            extra={"integration_api_key": apikey}
        )

        url = f"{self.sensors_api_endpoint}/{endpoint}/"

        request = dict(
            url=url,
            headers={"apikey": apikey}
        )

        clean_batch = json.loads(json.dumps(data, default=str))
        request["json"] = clean_batch

        logger.debug(
            f" -- sending {endpoint}. --",
            extra={
                "length": len(clean_batch),
                "api": url,
            },
        )

        async with httpx.AsyncClient(timeout=120) as session:
            client_response = await session.patch(**request)

        errors.raise_for_status(client_response)

        return client_response.json()


class GundiClient:
    DEFAULT_CONNECT_TIMEOUT_SECONDS = 3.1
    DEFAULT_DATA_TIMEOUT_SECONDS = 20
    DEFAULT_CONNECTION_RETRIES = 5

    def __init__(self, **kwargs):
        # API settings
        self.gundi_version = "v2"
        self.base_url = kwargs.get("base_url", settings.GUNDI_API_BASE_URL)
        self.api_base_path = f"{self.base_url}/{self.gundi_version}"
        self.connections_endpoint = f"{self.api_base_path}/connections"
        self.integrations_endpoint = f"{self.api_base_path}/integrations"
        self.source_states_endpoint = f"{self.api_base_path}/sources/states"
        self.sources_endpoint = f"{self.api_base_path}/sources"
        self.routes_endpoint = f"{self.api_base_path}/routes"
        self.traces_endpoint = f"{self.api_base_path}/traces"

        # Authentication settings
        # New oauth_* names preferred; keycloak_* still accepted for backward compatibility
        self.ssl_verify = kwargs.get("use_ssl", settings.GUNDI_API_SSL_VERIFY)
        self.client_id = kwargs.get("oauth_client_id",
                                    kwargs.get("keycloak_client_id", settings.OAUTH_CLIENT_ID))
        self.client_secret = kwargs.get("oauth_client_secret",
                                        kwargs.get("keycloak_client_secret", settings.OAUTH_CLIENT_SECRET))
        self.username = kwargs.get("username", settings.GUNDI_USERNAME)
        self.password = kwargs.get("password", settings.GUNDI_PASSWORD)
        self.oauth_token_url = kwargs.get("oauth_token_url", settings.OAUTH_TOKEN_URL)
        self.oauth_issuer = kwargs.get("oauth_issuer", settings.OAUTH_ISSUER)
        self.audience = kwargs.get("oauth_audience",
                                   kwargs.get("keycloak_audience", settings.OAUTH_AUDIENCE))
        self.scope = kwargs.get("oauth_scope", settings.OAUTH_SCOPE)
        self.cached_token = None
        self.cached_token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)

        # Retries and timeouts settings
        self.max_retries = kwargs.get('max_http_retries', self.DEFAULT_CONNECTION_RETRIES)
        transport = AsyncHTTPTransport(retries=self.max_retries, verify=self.ssl_verify)
        connect_timeout = kwargs.get('connect_timeout', self.DEFAULT_CONNECT_TIMEOUT_SECONDS)
        data_timeout = kwargs.get('data_timeout', self.DEFAULT_DATA_TIMEOUT_SECONDS)
        timeout = Timeout(data_timeout, connect=connect_timeout, pool=connect_timeout)

        # Session
        self._session = AsyncClient(transport=transport, timeout=timeout)

    async def close(self):
        await self._session.aclose()

    # Support using this client as an async context manager.
    async def __aenter__(self):
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self._session.__aexit__()

    async def _get(self, url, params=None, headers=None, **kwargs):
        headers = headers or {}
        auth_headers = await self.get_auth_header()
        response = await self._session.get(
            url,
            params=params,
            headers={**auth_headers, **headers},
            **kwargs,
        )
        # Force refresh the token and retry if we get redirected to the login page
        if response.status_code == 302 and "auth/realms" in response.headers.get("location", ""):
            auth_headers = await self.get_auth_header(force_refresh_token=True)
            response = await self._session.get(
                url,
                params=params,
                headers={**auth_headers, **headers},
                **kwargs,
            )
        return response

    async def _post(self, url, data: dict = None, params=None, headers=None, **kwargs):
        headers = headers or {}
        auth_headers = await self.get_auth_header()
        response = await self._session.post(
            url,
            json=data,
            params=params,
            headers={**auth_headers, **headers},
            **kwargs,
        )
        # Force refresh the token and retry if we get redirected to the login page
        if response.status_code == 302 and "auth/realms" in response.headers.get("location", ""):
            auth_headers = await self.get_auth_header(force_refresh_token=True)
            response = await self._session.post(
                url,
                json=data,
                params=params,
                headers={**auth_headers, **headers},
                **kwargs,
            )
        return response

    async def _resolve_token_url(self) -> str:
        """Return the token endpoint URL. Explicit oauth_token_url wins; otherwise
        discover it from oauth_issuer via OIDC discovery. Discovery results are
        cached process-wide in auth._DISCOVERY_CACHE, so repeated calls with the
        same issuer are cheap (one dict lookup). Raises AuthenticationError if
        neither is set."""
        if self.oauth_token_url:
            return self.oauth_token_url
        if self.oauth_issuer:
            return await auth.discover_token_endpoint(self._session, self.oauth_issuer)
        raise errors.AuthenticationError(
            "No token URL configured. Set oauth_token_url or oauth_issuer."
        )

    async def _refresh_token(self):
        now = datetime.now(tz=timezone.utc)
        token_url = await self._resolve_token_url()

        # 1. Prefer the refresh-token grant when we hold a live refresh token.
        if (
            self.cached_token
            and self.cached_token.refresh_token
            and self.cached_token_refresh_expires_at > now
        ):
            try:
                token, refresh_rotated = await auth.refresh_access_token(
                    session=self._session,
                    oauth_token_url=token_url,
                    client_id=self.client_id,
                    refresh_token=self.cached_token.refresh_token,
                    fallback=self.cached_token,
                    # Public/password clients must not send a secret on refresh.
                    client_secret=None if (self.username and self.password) else self.client_secret,
                    scope=self.scope,
                )
                self._store_token(token, refresh_rotated=refresh_rotated)
                return token
            except errors.AuthenticationError:
                logger.info("Refresh-token grant failed; falling back to full re-authentication.")
                self.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)

        # 2. Full authentication. Password grant wins when user credentials are present.
        # A client_id is required for every grant we support, so guard the password
        # branch on it too — otherwise we'd send a half-formed request and let the IdP
        # reject it remotely instead of failing locally with a clear configuration error.
        if self.username and self.password and self.client_id:
            logger.debug("Authenticating via password grant.")
            token = await auth.get_access_token_password_grant(
                session=self._session,
                oauth_token_url=token_url,
                client_id=self.client_id,
                username=self.username,
                password=self.password,
                audience=self.audience,
                scope=self.scope,
            )
        elif self.client_id and self.client_secret:
            logger.debug("Authenticating via client_credentials grant.")
            token = await auth.get_access_token_client_credentials(
                session=self._session,
                oauth_token_url=token_url,
                client_id=self.client_id,
                client_secret=self.client_secret,
                audience=self.audience,
                scope=self.scope,
            )
        else:
            raise errors.AuthenticationError(
                "No credentials configured. Provide a client_id with either "
                "username/password (public client) or client_secret (confidential client)."
            )
        self._store_token(token)
        return token

    def _store_token(self, token, *, refresh_rotated=True):
        # OAuthToken (gundi-core) always carries access + refresh fields on a successful parse,
        # but for grants that don't issue refresh tokens (e.g. client_credentials) the auth
        # helper backfills empty refresh_token and refresh_expires_in=0. Detect that here.
        # ``refresh_rotated`` is False only when this token came from a refresh-grant response
        # that omitted a new refresh_token (RFC 6749 §6) — in that case we preserve the
        # existing cached_token_refresh_expires_at because the cached refresh token is still
        # valid for its original lifetime.
        now = datetime.now(tz=timezone.utc)
        self.cached_token = token
        self.cached_token_expires_at = now + timedelta(
            seconds=self._expiry_with_buffer(token.expires_in)
        )
        if refresh_rotated:
            # `> 0` treats both zero (the backfilled refreshless case) and any negative
            # `refresh_expires_in` (server bug / weird IdP) as 'no refresh available'.
            if token.refresh_token and token.refresh_expires_in > 0:
                self.cached_token_refresh_expires_at = now + timedelta(
                    seconds=self._expiry_with_buffer(token.refresh_expires_in)
                )
            else:
                # Refreshless grant — disable refresh tracking so the refresh-token
                # branch in _refresh_token doesn't pick this up.
                self.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)

    @staticmethod
    def _expiry_with_buffer(lifetime_seconds, buffer_seconds=15):
        # Subtract a clock-skew buffer, but never more than half the lifetime, so a short-lived
        # token is not treated as already expired (which would re-authenticate on every call).
        return max(lifetime_seconds - buffer_seconds, lifetime_seconds // 2)

    async def get_access_token(self, force_refresh_token=False) -> OAuthToken:
        if force_refresh_token or not self.cached_token or self.cached_token_expires_at < datetime.now(tz=timezone.utc):
            return await self._refresh_token()
        return self.cached_token

    async def get_auth_header(self, force_refresh_token=False) -> dict:
        token_object = await self.get_access_token(force_refresh_token=force_refresh_token)
        return {
            "authorization": f"{token_object.token_type} {token_object.access_token}"
        }

    @staticmethod
    def _raise_for_status(response):
        errors.raise_for_status(response)

    @staticmethod
    def _parse_list_response(data, model):
        if isinstance(data, list):
            return parse_obj_as(List[model], data)
        if isinstance(data, dict) and "results" in data:
            return parse_obj_as(List[model], data["results"])
        return [model.parse_obj(data)]

    async def get_connections(self, params: dict = None) -> List[Connection]:
        url = f"{self.connections_endpoint}/"
        response = await self._get(url, params=params)
        self._raise_for_status(response)
        return self._parse_list_response(response.json(), Connection)

    async def get_connection_details(self, integration_id):
        url = f"{self.connections_endpoint}/{integration_id}/"
        response = await self._get(url)
        self._raise_for_status(response)
        data = response.json()
        return Connection.parse_obj(data)

    async def get_route_details(self, route_id):
        url = f"{self.routes_endpoint}/{route_id}/"
        response = await self._get(url)
        self._raise_for_status(response)
        data = response.json()
        return Route.parse_obj(data)

    async def get_integrations(self, params: dict = None) -> AsyncGenerator[Integration, None]:
        url = f"{self.integrations_endpoint}/"
        while url:
            response = await self._get(url, params=params)
            self._raise_for_status(response)
            data = response.json()
            params = None  # the `next` URL already carries the query string
            for item in self._parse_list_response(data, Integration):
                yield item
            if isinstance(data, dict) and "results" in data:
                url = data.get("next") or ""
            else:
                return

    async def get_integration_details(self, integration_id):
        url = f"{self.integrations_endpoint}/{integration_id}/"
        response = await self._get(url)
        self._raise_for_status(response)
        data = response.json()
        return Integration.parse_obj(data)

    async def get_integration_api_key(self, integration_id):
        url = f"{self.integrations_endpoint}/{integration_id}/api-key/"
        response = await self._get(url)
        self._raise_for_status(response)
        data = response.json()
        return data.get("api_key")

    async def get_traces(self, params: dict):
        url = f"{self.traces_endpoint}/"
        response = await self._get(url, params=params)
        self._raise_for_status(response)
        data = response.json()["results"]
        return parse_obj_as(List[GundiTrace], data)

    async def register_integration_type(self, data: dict):
        url = f"{self.integrations_endpoint}/types/"
        response = await self._post(
            url,
            data=data,
        )
        self._raise_for_status(response)
        data = response.json()
        return IntegrationType.parse_obj(data)
