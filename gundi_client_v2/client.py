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
from typing import Any, AsyncGenerator, List, Optional
from uuid import UUID
from gundi_core.schemas import (
    OAuthToken,
)
from gundi_core.schemas.v2 import (
    Connection,
    Route,
    Integration,
    GundiTrace,
    IntegrationType,
)
from . import settings, errors
from . import auth
from . import token_cache as _token_cache

logger = logging.getLogger(__name__)
logger.setLevel(settings.LOG_LEVEL)


def _redact(secret: Optional[str]) -> str:
    """Mask a credential for logging.

    For secrets longer than 4 characters, returns ``****`` followed by the
    last 4 characters (preserves limited traceability across log lines).
    For secrets of 4 characters or fewer (or empty/None), returns ``****``
    with no tail — never leak short secrets in their entirety.
    """
    if not secret or len(secret) <= 4:
        return "****"
    return f"****{secret[-4:]}"


class GundiDataSenderClient:
    def __init__(self, integration_api_key: Optional[str] = None, **kwargs: Any):
        """Initialize the data-sender client for posting payloads to Gundi.

        Handles observations, events, messages, and event attachments. This
        client authenticates using an integration API key rather than OAuth
        and is intended for integrations that push data into Gundi via the
        sensors API. Obtain the key from
        ``GundiClient.get_integration_api_key(integration_id)``.

        Args:
            integration_api_key: The per-integration API key used as the
                ``apikey`` HTTP header on every request. May be left
                ``None`` at construction time (e.g. to be set later),
                but every method that issues a request will raise
                ``ValueError`` if the key is still missing when called.
            **kwargs: Optional keyword overrides.

                * ``sensors_api_base_url`` (str): Override the sensors API
                  base URL. Falls back to the ``SENSORS_API_BASE_URL``
                  environment variable.
        """
        self.gundi_version = "v2"
        self.sensors_api_endpoint = f"{kwargs.get('sensors_api_base_url', settings.SENSORS_API_BASE_URL)}/{self.gundi_version}"
        self._api_key = integration_api_key

    async def post_observations(self, data: List[dict]) -> Any:
        """Post a batch of observation records to Gundi.

        Args:
            data: List of observation dicts. Each dict should conform to the
                Gundi observation schema. Non-serialisable values (e.g.
                ``datetime`` objects) are automatically coerced to strings.

        Returns:
            The raw JSON response from the sensors API. Typically a list of
            envelopes, one per posted record.

        Raises:
            ValueError: If no ``integration_api_key`` was provided.
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        return await self._post_data(data=data, endpoint="observations")

    async def post_events(self, data: List[dict]) -> Any:
        """Post a batch of event records to Gundi.

        Args:
            data: List of event dicts. Each dict should conform to the
                Gundi event schema. Non-serialisable values are automatically
                coerced to strings.

        Returns:
            The raw JSON response from the sensors API. Typically a list of
            envelopes, one per posted record.

        Raises:
            ValueError: If no ``integration_api_key`` was provided.
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        return await self._post_data(data=data, endpoint="events")

    async def post_messages(self, data: List[dict]) -> Any:
        """Post a batch of message records to Gundi.

        Args:
            data: List of message dicts. Each dict should conform to the
                Gundi message schema. Non-serialisable values are
                automatically coerced to strings.

        Returns:
            The raw JSON response from the sensors API. Typically a list of
            envelopes, one per posted record.

        Raises:
            ValueError: If no ``integration_api_key`` was provided.
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
            ValueError: If no ``integration_api_key`` was provided.
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        return await self._update_data(data=data, endpoint=f"events/{event_id}")

    async def post_event_attachments(
        self, event_id: str, attachments: List[tuple]
    ) -> Any:
        """Upload file attachments for an existing event via multipart POST.

        Args:
            event_id: The UUID (or string ID) of the event to attach files to.
            attachments: List of ``(filename, file_binary)`` tuples where
                ``filename`` is a string (e.g. ``"photo.jpg"``) and
                ``file_binary`` is the raw bytes of the file.

        Returns:
            The raw JSON response from the sensors API. Typically a list of
            envelopes, one per posted record.

        Raises:
            ValueError: If no ``integration_api_key`` was provided.
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        return await self._post_data(
            attachments=attachments, endpoint=f"events/{event_id}/attachments"
        )

    async def _post_data(
        self,
        data: List[dict] = None,
        endpoint: str = None,
        attachments: List[tuple] = None,
    ) -> dict:
        apikey = self._api_key
        if apikey is None:
            raise ValueError(
                "GundiDataSenderClient requires an integration_api_key. "
                "Obtain one via GundiClient.get_integration_api_key(integration_id)."
            )

        logger.info(
            f" -- Posting to routing services --",
            extra={"integration_api_key": _redact(apikey)},
        )

        url = f"{self.sensors_api_endpoint}/{endpoint}/"

        request = dict(url=url, headers={"apikey": apikey})

        if data:
            clean_batch = [json.loads(json.dumps(r, default=str)) for r in data]
            request["json"] = clean_batch

        if attachments:
            request["files"] = [
                ("file", (filename, image_binary))
                for filename, image_binary in attachments
            ]

        logger.debug(
            f" -- sending {endpoint}. --",
            extra={
                "length": len(data if data is not None else (attachments or [])),
                "api": url,
            },
        )

        async with httpx.AsyncClient(timeout=120) as session:
            client_response = await session.post(**request)

        errors.raise_for_status(client_response)

        return client_response.json()

    async def _update_data(self, data: dict = None, endpoint: str = None) -> dict:
        apikey = self._api_key
        if apikey is None:
            raise ValueError(
                "GundiDataSenderClient requires an integration_api_key. "
                "Obtain one via GundiClient.get_integration_api_key(integration_id)."
            )

        logger.info(
            f" -- Updating data... --", extra={"integration_api_key": _redact(apikey)}
        )

        url = f"{self.sensors_api_endpoint}/{endpoint}/"

        request = dict(url=url, headers={"apikey": apikey})

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

    def __init__(self, **kwargs: Any):
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
                  OAuth client ID. Env: ``GUNDI_OAUTH_CLIENT_ID`` /
                  ``OAUTH_CLIENT_ID`` / ``KEYCLOAK_CLIENT_ID``.
                * ``oauth_client_secret`` / ``keycloak_client_secret``
                  (str): OAuth client secret (confidential clients). Env:
                  ``GUNDI_OAUTH_CLIENT_SECRET`` / ``OAUTH_CLIENT_SECRET`` /
                  ``KEYCLOAK_CLIENT_SECRET``.
                * ``username`` (str): Resource-owner username (password
                  grant). Env: ``GUNDI_USERNAME``.
                * ``password`` (str): Resource-owner password (password
                  grant). Env: ``GUNDI_PASSWORD``.
                * ``oauth_token_url`` (str): Direct token endpoint URL.
                  Takes precedence over ``oauth_issuer``. Env:
                  ``GUNDI_OAUTH_TOKEN_URL`` / ``OAUTH_TOKEN_URL``.
                * ``oauth_issuer`` (str): OIDC issuer URL. Used for
                  automatic token-endpoint discovery when
                  ``oauth_token_url`` is not set. Env:
                  ``GUNDI_OAUTH_ISSUER`` / ``OAUTH_ISSUER`` /
                  ``KEYCLOAK_ISSUER``.
                * ``oauth_audience`` / ``keycloak_audience`` (str): OAuth
                  audience claim. Required by Auth0; optional for
                  Keycloak. Env: ``GUNDI_OAUTH_AUDIENCE`` /
                  ``OAUTH_AUDIENCE`` / ``KEYCLOAK_AUDIENCE``.
                * ``oauth_scope`` (str): Space-separated OAuth scopes.
                  Env: ``GUNDI_OAUTH_SCOPE`` / ``OAUTH_SCOPE`` (default
                  ``"openid"``).

                **Token cache settings**

                * ``token_cache_url`` (str): Durable token cache backend
                  shared with other processes: ``redis://host:port/db``,
                  ``rediss://…`` or ``file:///dir``. Env:
                  ``GUNDI_TOKEN_CACHE_URL``. Unset means tokens are shared
                  only within this process (always on).
                * ``token_cache`` (TokenCache): An injected backend; takes
                  precedence over ``token_cache_url``.

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
        self.activity_logs_endpoint = f"{self.api_base_path}/logs"

        # Authentication settings
        # New oauth_* names preferred; keycloak_* still accepted for backward compatibility
        self.ssl_verify = kwargs.get("use_ssl", settings.GUNDI_API_SSL_VERIFY)
        self.client_id = kwargs.get(
            "oauth_client_id",
            kwargs.get("keycloak_client_id", settings.OAUTH_CLIENT_ID),
        )
        self.client_secret = kwargs.get(
            "oauth_client_secret",
            kwargs.get("keycloak_client_secret", settings.OAUTH_CLIENT_SECRET),
        )
        self.username = kwargs.get("username", settings.GUNDI_USERNAME)
        self.password = kwargs.get("password", settings.GUNDI_PASSWORD)
        self.oauth_token_url = kwargs.get("oauth_token_url", settings.OAUTH_TOKEN_URL)
        self.oauth_issuer = kwargs.get("oauth_issuer", settings.OAUTH_ISSUER)
        self.audience = kwargs.get(
            "oauth_audience", kwargs.get("keycloak_audience", settings.OAUTH_AUDIENCE)
        )
        self.scope = kwargs.get("oauth_scope", settings.OAUTH_SCOPE)
        self.cached_token = None
        self.cached_token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)

        # Shared token cache: process-wide memory layer, plus one optional backend.
        backend = kwargs.get("token_cache")
        if backend is None:
            backend = _token_cache.token_cache_from_url(
                kwargs.get("token_cache_url", settings.GUNDI_TOKEN_CACHE_URL)
            )
        self._token_store = _token_cache.TokenStore(backend)

        # Retries and timeouts settings
        self.max_retries = kwargs.get(
            "max_http_retries", self.DEFAULT_CONNECTION_RETRIES
        )
        transport = AsyncHTTPTransport(retries=self.max_retries, verify=self.ssl_verify)
        connect_timeout = kwargs.get(
            "connect_timeout", self.DEFAULT_CONNECT_TIMEOUT_SECONDS
        )
        data_timeout = kwargs.get("data_timeout", self.DEFAULT_DATA_TIMEOUT_SECONDS)
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
        return await self._session.__aexit__(exc_type, exc_value, traceback)

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
        if response.status_code == 302 and "auth/realms" in response.headers.get(
            "location", ""
        ):
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
        if response.status_code == 302 and "auth/realms" in response.headers.get(
            "location", ""
        ):
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
        if response.status_code == 302 and "auth/realms" in response.headers.get(
            "location", ""
        ):
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
        if response.status_code == 302 and "auth/realms" in response.headers.get(
            "location", ""
        ):
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

    def _grant_type(self) -> str:
        return "password" if (self.username and self.password) else "client_credentials"

    def _token_cache_key(self, token_url: str) -> str:
        # The username always scopes the key: a CLI profile client carries a
        # username and a restored token but no password, so several such
        # clients under one client id would otherwise share an entry and adopt
        # each other's tokens. (A client_credentials replica with an incidental
        # GUNDI_USERNAME therefore keys apart from one without; sharing across
        # replicas needs identical settings.) The password never enters the
        # key: a human password hashed next to guessable material would make
        # the key name an offline password verifier, and a changed password
        # does not invalidate tokens already issued. The client secret does
        # enter it: it is high-entropy, and a rotation must not reuse a token
        # minted under the old one.
        grant = self._grant_type()
        return _token_cache.token_cache_key(
            token_url=token_url,
            grant_type=grant,
            client_id=self.client_id,
            username=self.username,
            audience=self.audience,
            scope=self.scope,
            secret=None if grant == "password" else self.client_secret,
        )

    def _current_entry(self) -> "_token_cache.CachedToken | None":
        if self.cached_token is None:
            return None
        return _token_cache.CachedToken(
            access_token=self.cached_token.access_token,
            refresh_token=self.cached_token.refresh_token or "",
            token_type=self.cached_token.token_type or "Bearer",
            expires_at=self.cached_token_expires_at,
            refresh_expires_at=self.cached_token_refresh_expires_at,
        )

    def _adopt(self, entry: "_token_cache.CachedToken") -> None:
        """Make ``entry`` this instance's token. Keeps the three public
        attributes the CLI token store and callers read."""
        self.cached_token = entry.to_oauth_token()
        self.cached_token_expires_at = entry.expires_at
        self.cached_token_refresh_expires_at = entry.refresh_expires_at

    def _to_cached(
        self, token: OAuthToken, *, refresh_rotated: bool = True, prior=None
    ) -> "_token_cache.CachedToken":
        # ``refresh_rotated`` is False only when a refresh-grant response omitted a
        # new refresh_token (RFC 6749 §6): the prior refresh token and its lifetime
        # stay valid, so they are carried over.
        now = _token_cache._now()
        expires_at = now + timedelta(seconds=self._expiry_with_buffer(token.expires_in))
        if not refresh_rotated and prior is not None:
            refresh_expires_at = prior.refresh_expires_at
        elif token.refresh_token and token.refresh_expires_in > 0:
            refresh_expires_at = now + timedelta(
                seconds=self._expiry_with_buffer(token.refresh_expires_in)
            )
        else:
            refresh_expires_at = _token_cache.NO_REFRESH
        return _token_cache.CachedToken(
            access_token=token.access_token,
            refresh_token=token.refresh_token or "",
            token_type=token.token_type or "Bearer",
            expires_at=expires_at,
            refresh_expires_at=refresh_expires_at,
        )

    def _store_token(self, token, *, refresh_rotated=True):
        """Compatibility wrapper: adopt ``token`` onto this instance only."""
        self._adopt(
            self._to_cached(
                token, refresh_rotated=refresh_rotated, prior=self._current_entry()
            )
        )

    async def _fetch_token(self, token_url: str, prior) -> "_token_cache.CachedToken":
        """Get a token from the IdP: the refresh grant when ``prior`` holds a live
        refresh token, otherwise a full authentication.

        When both fail, the raised AuthenticationError carries
        ``refresh_token_rejected=True`` if the refresh grant was answered with
        ``invalid_grant`` on a 400 (Keycloak) or a 403 (Auth0), or with a bare
        400 (the refresh token itself is dead), rather than any other status
        (the refresh token may still be good). A transport failure on the
        refresh grant (``AuthenticationError.transport``, set by
        auth._post_token) is raised at once, without trying the full
        authentication on the same broken network; a malformed response body
        is not a transport failure and falls back like any other error."""
        now = _token_cache._now()
        refresh_rejected = False
        # 1. Prefer the refresh-token grant when we hold a live refresh token.
        if prior is not None and prior.refresh_is_live(now):
            fallback = prior.to_oauth_token(now)
            try:
                token, refresh_rotated = await auth.refresh_access_token(
                    session=self._session,
                    oauth_token_url=token_url,
                    client_id=self.client_id,
                    refresh_token=prior.refresh_token,
                    fallback=fallback,
                    # Public/password clients must not send a secret on refresh.
                    client_secret=(
                        None
                        if (self.username and self.password)
                        else self.client_secret
                    ),
                    scope=self.scope,
                )
                # An IdP that rotates the refresh token but omits refresh_expires_in
                # gets the fallback's remaining seconds backfilled; re-buffering that
                # would shave 15 s off the lifetime on every refresh. Carry the
                # prior absolute expiry instead.
                carried = token.refresh_expires_in == fallback.refresh_expires_in
                return self._to_cached(
                    token, refresh_rotated=refresh_rotated and not carried, prior=prior
                )
            except errors.AuthenticationError as e:
                if e.transport:
                    # No response at all: the network that just failed would
                    # fail the full authentication too, and the credentials
                    # should not go down a broken connection. One attempt. (A
                    # malformed 2xx body is a response; the full grant may work.)
                    raise
                # `invalid_grant` on a 400 (Keycloak) or 403 (Auth0) is the IdP's
                # verdict on the refresh token (RFC 6749 §5.2); a bare 400 with
                # no error code is taken the same way. Any other status, whatever
                # its body says, is not a verdict on the refresh token.
                refresh_rejected = (
                    e.status_code == 400 and e.error in (None, "invalid_grant")
                ) or (e.status_code == 403 and e.error == "invalid_grant")
                logger.info(
                    "Refresh-token grant failed; falling back to full re-authentication."
                )
        try:
            return await self._authenticate(token_url)
        except errors.AuthenticationError as e:
            e.refresh_token_rejected = refresh_rejected
            raise

    async def _authenticate(self, token_url: str) -> "_token_cache.CachedToken":
        """Full authentication with the configured grant."""
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
        return self._to_cached(token)

    async def _refresh_token(self):
        """Compatibility wrapper around _fetch_token for callers of the old name."""
        entry = await self._fetch_token(
            await self._resolve_token_url(), self._current_entry()
        )
        self._adopt(entry)
        return self.cached_token

    @staticmethod
    def _expiry_with_buffer(lifetime_seconds, buffer_seconds=15):
        # Subtract a clock-skew buffer, but never more than half the lifetime, so a short-lived
        # token is not treated as already expired (which would re-authenticate on every call).
        return max(lifetime_seconds - buffer_seconds, lifetime_seconds // 2)

    async def get_access_token(self, force_refresh_token: bool = False) -> OAuthToken:
        """Return a valid OAuth access token, reusing one from the shared cache
        when possible and refreshing or re-authenticating when necessary.

        Lookup order: this instance's token, the process-wide memory layer, the
        configured backend (Redis or file), then the IdP (refresh grant when a
        live refresh token is known, else full authentication). Whatever is
        fetched is written to every layer. ``force_refresh_token=True`` (which
        the request helpers pass after the API's login redirect) first evicts
        the shared entry so no other client or replica keeps serving a token
        the server has rejected.

        Args:
            force_refresh_token: When ``True``, evict the cached entry and
                fetch a fresh token from the IdP.

        Returns:
            A valid ``OAuthToken``.

        Raises:
            AuthenticationError: If no credentials are configured or the IdP
                rejects the request.
        """
        now = _token_cache._now()
        if (
            not force_refresh_token
            and self.cached_token is not None
            and self.cached_token_expires_at > now
        ):
            return self.cached_token
        token_url = await self._resolve_token_url()
        key = self._token_cache_key(token_url)
        async with self._token_store.lock(key):
            prior = self._current_entry()
            if force_refresh_token:
                # Evict only the token this instance was rejected on. A sibling
                # (in this process or another) may already have replaced it;
                # adopting that replacement avoids evicting a fresh token and
                # replaying an already-exchanged refresh token. An instance with
                # no token of its own (`gundi auth login` validating typed
                # credentials) always goes to the IdP.
                shared = await self._token_store.reload(key)
                if (
                    prior is not None
                    and shared is not None
                    and shared.is_live(_token_cache._now())
                    and shared.access_token != prior.access_token
                ):
                    self._adopt(shared)
                    return self.cached_token
                await self._token_store.delete(key)
            else:
                shared = await self._token_store.get(key)
                if shared is not None:
                    if shared.is_live(_token_cache._now()):
                        self._adopt(shared)
                        return self.cached_token
                    prior = (
                        shared  # expired access token; its refresh token may still work
                    )
            try:
                entry = await self._fetch_token(token_url, prior)
            except errors.AuthenticationError as e:
                if force_refresh_token:
                    # The instance's token was rejected and could not be
                    # replaced: nothing about it may be served again.
                    self.cached_token = None
                    self.cached_token_expires_at = _token_cache.NO_REFRESH
                    self.cached_token_refresh_expires_at = _token_cache.NO_REFRESH
                elif e.refresh_token_rejected:
                    # The IdP refused the refresh token itself (invalid_grant, or
                    # a bare 400): drop the shared entry so no replica replays
                    # it, and stop this instance from trying it again. Any other
                    # failure leaves everything in place; the token may be fine.
                    await self._token_store.delete(key)
                    if self.cached_token is not None:
                        self.cached_token_refresh_expires_at = _token_cache.NO_REFRESH
                raise
            await self._token_store.set(key, entry)
            self._adopt(entry)
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
        token_object = await self.get_access_token(
            force_refresh_token=force_refresh_token
        )
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

    async def get_connection_details(self, integration_id: str | UUID) -> Connection:
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

    async def get_routes_for_connection(self, connection_id: str | UUID) -> List[Route]:
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

    async def get_route_details(self, route_id: str | UUID) -> Route:
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

    async def update_route(self, route_id: str | UUID, data: dict) -> Route:
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

    async def delete_route(self, route_id: str | UUID) -> None:
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

    async def get_integrations(
        self, params: dict = None
    ) -> AsyncGenerator[Integration, None]:
        """Iterate over all Integrations, walking pagination automatically.

        Unlike ``get_connections()`` and ``get_routes()`` which return the
        first page only, this method is an async generator that follows the
        ``next`` cursor returned by the API until all pages are exhausted.

        Usage::

            async for integration in client.get_integrations():
                print(integration.id)

        Args:
            params: Optional dict of query parameters for the first
                request. Common keys: ``type`` (integration type **UUID**,
                not the slug — resolve a slug via ``get_integration_types``),
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

    async def get_integration_types(
        self, params: dict = None
    ) -> AsyncGenerator[IntegrationType, None]:
        """Iterate over all IntegrationTypes, walking pagination automatically.

        Mirrors ``get_integrations``: an async generator that follows the
        ``next`` cursor until all pages are exhausted. Useful for resolving an
        integration type slug (``IntegrationType.value``) to its ``id`` for the
        ``type`` filter on ``get_integrations``.

        Usage::

            async for itype in client.get_integration_types():
                print(itype.value, itype.id)

        Args:
            params: Optional dict of query parameters for the first request.
                Subsequent page requests use the cursor embedded in the
                ``next`` URL and ignore this dict.

        Yields:
            ``IntegrationType`` objects across all pages.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response on any
                page request.
        """
        url = f"{self.integrations_endpoint}/types/"
        while url:
            response = await self._get(url, params=params)
            self._raise_for_status(response)
            data = response.json()
            params = None  # the `next` URL already carries the query string
            for item in self._parse_list_response(data, IntegrationType):
                yield item
            if isinstance(data, dict) and "results" in data:
                url = data.get("next") or ""
            else:
                return

    async def get_activity_logs(
        self, params: dict = None
    ) -> AsyncGenerator[dict, None]:
        """Iterate over activity logs, walking pagination automatically.

        Logs are returned newest-first (the API orders by ``-created_at``).
        ``gundi_core`` has no ActivityLog schema, so each entry is yielded as a
        raw ``dict`` rather than a parsed model.

        Usage::

            async for log in client.get_activity_logs(params={"integration": id}):
                print(log["created_at"], log["value"])

        Args:
            params: Optional dict of query parameters for the first request.
                Common keys: ``integration`` (integration id), ``integration__in``
                (comma-separated ids), ``log_level``, ``log_type``, ``from_date``,
                ``to_date``. Subsequent page requests use the cursor embedded in
                the ``next`` URL and ignore this dict.

        Yields:
            ``dict`` log entries across all pages, newest first.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response on any
                page request.
        """
        url = f"{self.activity_logs_endpoint}/"
        while url:
            response = await self._get(url, params=params)
            self._raise_for_status(response)
            data = response.json()
            params = None  # the `next` URL already carries the query string
            if isinstance(data, dict) and "results" in data:
                items = data["results"]
                url = data.get("next") or ""
            else:
                items = data if isinstance(data, list) else []
                url = ""
            for item in items:
                yield item

    async def get_integration_details(self, integration_id: str | UUID) -> Integration:
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

    async def update_integration(
        self, integration_id: str | UUID, data: dict
    ) -> Integration:
        """Partially update an Integration via HTTP PATCH.

        Only the fields present in ``data`` are modified; omitted fields
        retain their current values on the server (standard PATCH
        semantics).

        To update an action configuration, pass a ``configurations`` list
        whose entries carry the configuration ``id`` and the new ``data``::

            await client.update_integration(
                integration_id,
                {"configurations": [{"id": config_id, "data": {...}}]},
            )

        See ``update_integration_configuration()`` for a convenience wrapper
        around that common case.

        Args:
            integration_id: UUID of the Integration to update.
            data: Partial dict of fields to update.

        Returns:
            The updated ``Integration``, re-fetched via
            ``get_integration_details``. (The PATCH response itself is
            serialized with the write serializer, which renders ``type`` /
            ``owner`` / action references as bare ids rather than the nested
            objects the ``Integration`` schema requires — so we re-read the
            canonical representation instead of parsing the PATCH body.)

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        url = f"{self.integrations_endpoint}/{integration_id}/"
        response = await self._patch(url, data=data)
        self._raise_for_status(response)
        return await self.get_integration_details(integration_id)

    async def update_integration_configuration(
        self,
        integration_id: str | UUID,
        configuration_id: str | UUID,
        data: dict,
    ) -> Integration:
        """Update a single action configuration's ``data`` on an Integration.

        Convenience wrapper around ``update_integration()`` for the common
        case of rewriting one action configuration's payload (e.g. updating
        a destination's field/tag mappings). The configuration is matched by
        its ``id``; its action binding is left unchanged.

        Args:
            integration_id: UUID of the Integration that owns the configuration.
            configuration_id: UUID of the action configuration to update.
            data: The new ``data`` payload for that configuration.

        Returns:
            The updated ``Integration`` object as returned by the API.

        Raises:
            AuthenticationError: If the OAuth token request fails.
            GundiAPIError: If the API returns a 4xx/5xx response.
        """
        return await self.update_integration(
            integration_id,
            {"configurations": [{"id": str(configuration_id), "data": data}]},
        )

    async def get_integration_api_key(
        self, integration_id: str | UUID
    ) -> Optional[str]:
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
