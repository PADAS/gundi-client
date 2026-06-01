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
from typing import AsyncGenerator, List, Optional
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
        """Initialize the data-sender client for posting observations and events.

        This client authenticates using an integration API key rather than OAuth
        and is intended for integrations that push data into Gundi via the
        sensors API. Obtain the key from
        ``GundiClient.get_integration_api_key(integration_id)``.

        Args:
            integration_api_key: The per-integration API key used as the
                ``apikey`` HTTP header on every request. Falls back to
                ``None`` (requests will be rejected by the server) if
                omitted.
            **kwargs: Optional keyword overrides.

                * ``sensors_api_base_url`` (str): Override the sensors API
                  base URL. Falls back to the ``SENSORS_API_BASE_URL``
                  environment variable.
        """
        self.gundi_version = "v2"
        self.sensors_api_endpoint = (
            f"{kwargs.get('sensors_api_base_url', settings.SENSORS_API_BASE_URL)}/{self.gundi_version}"
        )
        self._api_key = integration_api_key

    async def post_observations(self, data: List[dict]) -> dict:
        """Post a batch of observation records to Gundi.

        Args:
            data: List of observation dicts. Each dict should conform to the
                Gundi observation schema. Non-serialisable values (e.g.
                ``datetime`` objects) are automatically coerced to strings.

        Returns:
            The raw JSON response body returned by the sensors API.

        Raises:
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        return await self._post_data(data=data, endpoint="observations")

    async def post_events(self, data: List[dict]) -> dict:
        """Post a batch of event records to Gundi.

        Args:
            data: List of event dicts. Each dict should conform to the
                Gundi event schema. Non-serialisable values are automatically
                coerced to strings.

        Returns:
            The raw JSON response body returned by the sensors API.

        Raises:
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        return await self._post_data(data=data, endpoint="events")

    async def post_messages(self, data: List[dict]) -> dict:
        """Post a batch of message records to Gundi.

        Args:
            data: List of message dicts. Each dict should conform to the
                Gundi message schema. Non-serialisable values are
                automatically coerced to strings.

        Returns:
            The raw JSON response body returned by the sensors API.

        Raises:
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        return await self._post_data(data=data, endpoint="messages")

    async def update_event(self, event_id: str, data: dict) -> dict:
        """Partially update an existing event via HTTP PATCH.

        Only the fields present in ``data`` are modified; omitted fields
        retain their current values on the server (standard PATCH semantics).

        Args:
            event_id: The UUID (or string ID) of the event to update.
            data: Dict of fields to update. Non-serialisable values are
                automatically coerced to strings.

        Returns:
            The raw JSON response body returned by the sensors API,
            representing the updated event.

        Raises:
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        return await self._update_data(data=data, endpoint=f"events/{event_id}")

    async def post_event_attachments(self, event_id: str, attachments: List[tuple]) -> dict:
        """Upload file attachments for an existing event via multipart POST.

        Args:
            event_id: The UUID (or string ID) of the event to attach files to.
            attachments: List of ``(filename, file_binary)`` tuples where
                ``filename`` is a string (e.g. ``"photo.jpg"``) and
                ``file_binary`` is the raw bytes of the file.

        Returns:
            The raw JSON response body returned by the sensors API.

        Raises:
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
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
        """Initialize the Gundi API client.

        All parameters are optional and fall back to the corresponding
        environment variable when not supplied.

        Args:
            **kwargs: Keyword overrides for client behaviour.

                **API settings**

                * ``base_url`` (str): Gundi API base URL. Env:
                  ``GUNDI_API_BASE_URL``.
                * ``use_ssl`` (bool): Whether to verify TLS certificates.
                  Env: ``GUNDI_API_SSL_VERIFY`` (default ``True``).

                **Authentication settings**

                The preferred kwarg names use the ``oauth_`` prefix.
                The legacy ``keycloak_`` prefix is still accepted for
                backward compatibility and is silently mapped to the same
                setting.

                * ``oauth_client_id`` / ``keycloak_client_id`` (str):
                  OAuth client ID. Env: ``OAUTH_CLIENT_ID`` /
                  ``KEYCLOAK_CLIENT_ID``.
                * ``oauth_client_secret`` / ``keycloak_client_secret``
                  (str): OAuth client secret (confidential clients). Env:
                  ``OAUTH_CLIENT_SECRET`` / ``KEYCLOAK_CLIENT_SECRET``.
                * ``username`` (str): Resource-owner username (password
                  grant). Env: ``GUNDI_USERNAME``.
                * ``password`` (str): Resource-owner password (password
                  grant). Env: ``GUNDI_PASSWORD``.
                * ``oauth_token_url`` (str): Direct token endpoint URL.
                  Takes precedence over ``oauth_issuer``. Env:
                  ``OAUTH_TOKEN_URL``.
                * ``oauth_issuer`` (str): OIDC issuer URL. Used for
                  automatic token-endpoint discovery when
                  ``oauth_token_url`` is not set. Env: ``OAUTH_ISSUER`` /
                  ``KEYCLOAK_ISSUER``.
                * ``oauth_audience`` / ``keycloak_audience`` (str): OAuth
                  audience claim. Required by Auth0; optional for
                  Keycloak. Env: ``OAUTH_AUDIENCE`` /
                  ``KEYCLOAK_AUDIENCE``.
                * ``oauth_scope`` (str): Space-separated OAuth scopes.
                  Env: ``OAUTH_SCOPE`` (default ``"openid"``).

                **Retry / timeout settings**

                * ``max_http_retries`` (int): Number of automatic HTTP
                  retries on transport errors (default ``5``).
                * ``connect_timeout`` (float): TCP connect timeout in
                  seconds (default ``3.1``).
                * ``data_timeout`` (float): Read/write timeout in seconds
                  (default ``20``).
        """
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
        """Close the underlying HTTPX async session.

        Call this when you are finished with the client and are not using
        it as an async context manager. After calling ``close()``, the
        client should not be used again.
        """
        await self._session.aclose()

    # Support using this client as an async context manager.
    async def __aenter__(self):
        """Enter the async context manager, returning this client instance."""
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Exit the async context manager, closing the underlying session."""
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

    async def _patch(self, url, data: dict = None, params=None, headers=None, **kwargs):
        headers = headers or {}
        auth_headers = await self.get_auth_header()
        response = await self._session.patch(
            url,
            json=data,
            params=params,
            headers={**auth_headers, **headers},
            **kwargs,
        )
        if response.status_code == 302 and "auth/realms" in response.headers.get("location", ""):
            auth_headers = await self.get_auth_header(force_refresh_token=True)
            response = await self._session.patch(
                url,
                json=data,
                params=params,
                headers={**auth_headers, **headers},
                **kwargs,
            )
        return response

    async def _delete(self, url, params=None, headers=None, **kwargs):
        headers = headers or {}
        auth_headers = await self.get_auth_header()
        response = await self._session.delete(
            url,
            params=params,
            headers={**auth_headers, **headers},
            **kwargs,
        )
        if response.status_code == 302 and "auth/realms" in response.headers.get("location", ""):
            auth_headers = await self.get_auth_header(force_refresh_token=True)
            response = await self._session.delete(
                url,
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

    async def get_access_token(self, force_refresh_token: bool = False) -> OAuthToken:
        """Return a valid OAuth access token, refreshing it when necessary.

        The token is cached in memory. On each call the expiry time is
        checked (with a 15-second clock-skew buffer). If the token has
        expired — or ``force_refresh_token`` is ``True`` — a new token is
        fetched from the IdP using the refresh-token grant (when a live
        refresh token is available) or a fresh full authentication.

        Args:
            force_refresh_token: When ``True``, bypass the cache and
                always fetch a fresh token from the IdP, even if the
                cached token has not yet expired.

        Returns:
            A valid ``OAuthToken`` object containing ``access_token``,
            ``token_type``, ``expires_in``, and related fields.

        Raises:
            AuthenticationError: If token retrieval fails (bad
                credentials, unreachable IdP, or missing configuration).
        """
        if force_refresh_token or not self.cached_token or self.cached_token_expires_at < datetime.now(tz=timezone.utc):
            return await self._refresh_token()
        return self.cached_token

    async def get_auth_header(self, force_refresh_token: bool = False) -> dict:
        """Return the ``Authorization`` header dict for the current access token.

        Convenience wrapper around ``get_access_token()`` that formats the
        token as a ready-to-merge header dict.

        Args:
            force_refresh_token: Passed through to ``get_access_token()``.
                When ``True``, a fresh token is fetched from the IdP
                before building the header.

        Returns:
            A dict with a single key ``"authorization"`` whose value is
            ``"<token_type> <access_token>"`` (e.g.
            ``"Bearer eyJ..."``) suitable for merging into an
            ``httpx`` request's ``headers``.

        Raises:
            AuthenticationError: If token retrieval fails.
        """
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
        """List Connections accessible to the authenticated principal.

        Returns the first page of results only (the Gundi API default
        page size is 20). For paginated walking, see the Pagination recipe
        in the docs.

        Args:
            params: Optional dict of query parameters passed through to
                the API. Common keys: ``status`` (``healthy``,
                ``unhealthy``, ``disabled``), ``owner`` (organization ID),
                ``search`` (substring match).

        Returns:
            List of ``Connection`` objects.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        url = f"{self.connections_endpoint}/"
        response = await self._get(url, params=params)
        self._raise_for_status(response)
        return self._parse_list_response(response.json(), Connection)

    async def get_connection_details(self, integration_id) -> Connection:
        """Retrieve full details for a single Connection.

        Args:
            integration_id: UUID of the Connection (integration) to look up.

        Returns:
            A ``Connection`` object with all fields populated.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response (e.g. 404
                if the connection does not exist or is not accessible).
        """
        url = f"{self.connections_endpoint}/{integration_id}/"
        response = await self._get(url)
        self._raise_for_status(response)
        data = response.json()
        return Connection.parse_obj(data)

    async def get_routes(self, params: dict = None) -> List[Route]:
        """List Routes accessible to the authenticated principal.

        Returns the first page of results only (Gundi API default page
        size is 20). To filter by provider connection, prefer the
        convenience method ``get_routes_for_connection()``.

        Args:
            params: Optional dict of query parameters. Common keys:
                ``provider`` (Connection UUID), ``destination``
                (Connection UUID), ``owner`` (organization ID),
                ``search`` (substring match).

        Returns:
            List of ``Route`` objects.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        url = f"{self.routes_endpoint}/"
        response = await self._get(url, params=params)
        self._raise_for_status(response)
        return self._parse_list_response(response.json(), Route)

    async def get_routes_for_connection(self, connection_id) -> List[Route]:
        """List Routes where the given Connection appears as a data provider.

        Convenience wrapper around ``get_routes(params={"provider": ...})``.
        To combine the provider filter with other server-side filters (e.g.
        ``owner``, ``destination``), call ``get_routes()`` directly with a
        merged params dict.

        Like ``get_routes``, this returns only the first page of results.
        For paginated walking see the Pagination recipe in the docs.

        Args:
            connection_id: UUID (or stringifiable ID) of the Connection to
                filter by.

        Returns:
            List of ``Route`` objects where ``connection_id`` is a provider.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        return await self.get_routes(params={"provider": str(connection_id)})

    async def get_route_details(self, route_id) -> Route:
        """Retrieve full details for a single Route.

        Args:
            route_id: UUID of the Route to look up.

        Returns:
            A ``Route`` object with all fields populated.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response (e.g. 404
                if the route does not exist or is not accessible).
        """
        url = f"{self.routes_endpoint}/{route_id}/"
        response = await self._get(url)
        self._raise_for_status(response)
        data = response.json()
        return Route.parse_obj(data)

    async def create_route(self, data: dict) -> Route:
        """Create a new Route via HTTP POST.

        Args:
            data: Dict describing the new route. Expected keys:

                * ``name`` (str, required): Human-readable route name.
                * ``owner`` (str, required): Organization UUID that owns
                  the route.
                * ``data_providers`` (list of str, required): UUIDs of
                  Connection objects that act as data sources.
                * ``destinations`` (list of str, required): UUIDs of
                  Connection objects that receive the data.
                * ``configuration`` (dict, optional): Route-level
                  configuration overrides.

        Returns:
            The newly created ``Route`` object as returned by the API.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response (e.g.
                400 for validation errors, 403 for insufficient
                permissions).
        """
        url = f"{self.routes_endpoint}/"
        response = await self._post(url, data=data)
        self._raise_for_status(response)
        return Route.parse_obj(response.json())

    async def update_route(self, route_id, data: dict) -> Route:
        """Partially update a Route via HTTP PATCH.

        Only the fields present in ``data`` are modified; omitted fields
        retain their current values on the server (standard PATCH
        semantics).

        Args:
            route_id: UUID of the Route to update.
            data: Partial dict of fields to update. Any subset of the
                keys accepted by ``create_route()`` is valid.

        Returns:
            The updated ``Route`` object as returned by the API.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        url = f"{self.routes_endpoint}/{route_id}/"
        response = await self._patch(url, data=data)
        self._raise_for_status(response)
        return Route.parse_obj(response.json())

    async def delete_route(self, route_id) -> None:
        """Delete a Route via HTTP DELETE.

        Args:
            route_id: UUID of the Route to delete.

        Returns:
            ``None``. The Gundi API returns HTTP 204 No Content on
            success.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response (e.g.
                404 if the route does not exist, 403 for insufficient
                permissions).
        """
        url = f"{self.routes_endpoint}/{route_id}/"
        response = await self._delete(url)
        self._raise_for_status(response)
        # 204 No Content on success — no body to return.

    async def get_integrations(self, params: dict = None) -> AsyncGenerator[Integration, None]:
        """Iterate over all Integrations, walking pagination automatically.

        Unlike ``get_connections()`` and ``get_routes()`` which return the
        first page only, this method is an async generator that follows the
        ``next`` cursor returned by the API until all pages are exhausted.

        Usage::

            async for integration in client.get_integrations():
                print(integration.id)

        Args:
            params: Optional dict of query parameters for the first
                request. Common keys: ``type`` (integration type slug),
                ``owner`` (organization ID), ``search`` (substring match).
                Subsequent page requests use the cursor embedded in the
                ``next`` URL and ignore this dict.

        Yields:
            ``Integration`` objects, one per integration, across all
            pages.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response on any
                page request.
        """
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

    async def get_integration_details(self, integration_id) -> Integration:
        """Retrieve full details for a single Integration.

        Args:
            integration_id: UUID of the Integration to look up.

        Returns:
            An ``Integration`` object with all fields populated.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response (e.g.
                404 if the integration does not exist or is not
                accessible).
        """
        url = f"{self.integrations_endpoint}/{integration_id}/"
        response = await self._get(url)
        self._raise_for_status(response)
        data = response.json()
        return Integration.parse_obj(data)

    async def get_integration_api_key(self, integration_id) -> Optional[str]:
        """Return the API key string for an Integration.

        This is the key passed as ``integration_api_key`` to
        ``GundiDataSenderClient``. Note: this method returns the **plain
        string** value of the key, not a dict or object — a common point
        of confusion.

        Args:
            integration_id: UUID of the Integration whose API key is
                requested.

        Returns:
            The API key as a plain string, or ``None`` if the response did
            not contain an ``api_key`` field. Callers should defensively
            check for ``None`` before passing the value to
            ``GundiDataSenderClient``.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response (e.g.
                403 if the caller lacks permission to read the key).
        """
        url = f"{self.integrations_endpoint}/{integration_id}/api-key/"
        response = await self._get(url)
        self._raise_for_status(response)
        data = response.json()
        return data.get("api_key")

    async def get_traces(self, params: dict) -> List[GundiTrace]:
        """List Gundi data traces (first page only).

        Traces record the routing history of individual data points through
        the Gundi pipeline and are useful for debugging delivery issues.

        Args:
            params: Dict of query parameters. Common keys:
                ``object_id`` (source record UUID), ``integration``
                (integration UUID), ``created_at__gte`` /
                ``created_at__lte`` (ISO-8601 datetime bounds).

        Returns:
            List of ``GundiTrace`` objects from the first result page.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        url = f"{self.traces_endpoint}/"
        response = await self._get(url, params=params)
        self._raise_for_status(response)
        data = response.json()["results"]
        return parse_obj_as(List[GundiTrace], data)

    async def register_integration_type(self, data: dict) -> IntegrationType:
        """Register or update an IntegrationType in the Gundi portal.

        This is an administrative operation typically called by integration
        services on startup (when ``REGISTER_ON_START=true``) to declare
        their capabilities, configuration schema, and webhook endpoints to
        Gundi.

        Args:
            data: Dict describing the integration type. Consult the Gundi
                API documentation for the full schema; commonly includes
                ``name``, ``description``, ``type_slug``,
                ``service_url``, and ``actions``.

        Returns:
            The created or updated ``IntegrationType`` object as returned
            by the API.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        url = f"{self.integrations_endpoint}/types/"
        response = await self._post(
            url,
            data=data,
        )
        self._raise_for_status(response)
        data = response.json()
        return IntegrationType.parse_obj(data)
