import logging

import httpx
from gundi_core.schemas import OAuthToken
from pydantic import ValidationError

from .errors import AuthenticationError

logger = logging.getLogger(__name__)


def _oauth_error_code(response: httpx.Response) -> "str | None":
    """The RFC 6749 §5.2 ``error`` code of a token-error response, if any."""
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    return error if isinstance(error, str) else None


def _extract_oauth_error(response: httpx.Response) -> str:
    """Build a detail string from an RFC 6749 §5.2 token-error response."""
    status = response.status_code
    try:
        body = response.json()
    except ValueError:
        return f"Token request failed: HTTP {status}"
    # RFC 6749 §5.2 errors are JSON objects, but a malformed server could return
    # a non-object (string, list, number, null). Fall back to a status-only message
    # so this helper cannot raise AttributeError out of _post_token's except path.
    if not isinstance(body, dict):
        return f"Token request failed: HTTP {status}"
    error = body.get("error", "unknown_error")
    description = body.get("error_description")
    if description:
        return f"Token request failed: HTTP {status} ({error}: {description})"
    return f"Token request failed: HTTP {status} ({error})"


async def _post_token(
    session: httpx.AsyncClient, oauth_token_url: str, payload: dict
) -> dict:
    """POST to the token endpoint; raise AuthenticationError on non-2xx or on
    a transport failure (so callers see one exception type for "no token")."""
    try:
        response = await session.post(oauth_token_url, data=payload)
    except httpx.HTTPError as e:  # connect/read/timeout: no response at all
        raise AuthenticationError(f"Token request failed: {e}") from e
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise AuthenticationError(
            _extract_oauth_error(e.response),
            status_code=e.response.status_code,
            error=_oauth_error_code(e.response),
        ) from e
    try:
        body = response.json()
    except ValueError as e:  # 2xx with a non-JSON body (e.g. a captive portal)
        raise AuthenticationError(
            f"Token endpoint {oauth_token_url} returned a non-JSON "
            f"{response.status_code} response"
        ) from e
    if not isinstance(body, dict):  # 2xx JSON that isn't an object (e.g. [] or "ok")
        raise AuthenticationError(
            f"Token endpoint {oauth_token_url} returned an unexpected "
            f"{response.status_code} response (not a JSON object)"
        )
    return body


async def _token_request(
    session: httpx.AsyncClient, oauth_token_url: str, payload: dict
) -> OAuthToken:
    """Thin wrapper around _post_token that coerces the response dict to OAuthToken."""
    try:
        return OAuthToken.parse_obj(
            await _post_token(session, oauth_token_url, payload)
        )
    except ValidationError as e:  # 2xx JSON missing the expected token fields
        raise AuthenticationError(
            f"Token endpoint {oauth_token_url} returned an unexpected response: {e}"
        ) from e


# NOTE: The Resource Owner Password Credentials (ROPC) grant is discouraged by OAuth 2.1
# (RFC 9700). It is supported here intentionally, for public clients that require it.
async def get_access_token_password_grant(
    session: httpx.AsyncClient,
    oauth_token_url: str,
    client_id: str,
    username: str,
    password: str,
    audience: str | None = None,
    scope: str = "openid",
) -> OAuthToken:
    """Obtain an access token via the OAuth2 Resource Owner Password Credentials grant.

    This grant is deprecated in OAuth 2.1 (RFC 9700) and should be avoided for
    new integrations. It is retained for backward compatibility with IdPs that
    do not support client_credentials for the required scopes.

    Args:
        session: An ``httpx.AsyncClient`` (or compatible) used for the HTTP request.
        oauth_token_url: The token endpoint URL of the authorization server.
        client_id: The OAuth2 client identifier registered with the IdP.
        username: The resource owner's username.
        password: The resource owner's password.
        audience: Optional audience string required by some IdPs (e.g. Auth0).
            Omit for IdPs that do not accept this parameter (e.g. Keycloak).
        scope: Space-separated OAuth2 scopes to request. Defaults to ``"openid"``.

    Returns:
        An ``OAuthToken`` containing the access token
        and related metadata.

    Raises:
        AuthenticationError: If the token endpoint returns a non-2xx response.
    """
    logger.debug(
        f"get_access_token (password grant) from {oauth_token_url} for user: {username}"
    )
    payload = {
        "client_id": client_id,
        "username": username,
        "password": password,
        "grant_type": "password",
        "scope": scope,
    }
    if audience:
        payload["audience"] = audience
    return await _token_request(session, oauth_token_url, payload)


async def refresh_access_token(
    session: httpx.AsyncClient,
    oauth_token_url: str,
    client_id: str,
    refresh_token: str,
    fallback: OAuthToken,
    client_secret: str | None = None,
    scope: str = "openid",
) -> tuple[OAuthToken, bool]:
    """Exchange a refresh token for a new access token (RFC 6749 §6).

    Args:
        session: An ``httpx.AsyncClient`` (or compatible) used for the HTTP request.
        oauth_token_url: The token endpoint URL of the authorization server.
        client_id: The OAuth2 client identifier registered with the IdP.
        refresh_token: The refresh token obtained from a previous token response.
        fallback: The previous ``OAuthToken`` used to
            backfill ``refresh_token`` and ``refresh_expires_in`` if the IdP
            response omits them (RFC 6749 §6 makes the new refresh token OPTIONAL).
        client_secret: Optional client secret for confidential clients.
        scope: Space-separated OAuth2 scopes to request. Defaults to ``"openid"``.

    Returns:
        A tuple ``(token, refresh_rotated)`` where ``token`` is a new
        ``OAuthToken`` and ``refresh_rotated`` is
        ``True`` when the IdP issued a new refresh token in the response,
        ``False`` when it omitted one (the fallback refresh metadata is reused).

    Raises:
        AuthenticationError: If the token endpoint returns a non-2xx response.
    """
    logger.debug(
        f"refresh_access_token from {oauth_token_url} using client_id: {client_id}"
    )
    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": scope,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    body = await _post_token(session, oauth_token_url, payload)
    # A rotation means the IdP issued a new, non-empty refresh token. A missing,
    # null, or empty value is NOT a rotation — reuse the prior refresh token and
    # its lifetime (OAuthToken requires both fields and rejects null).
    new_refresh_token = body.get("refresh_token")
    refresh_rotated = bool(new_refresh_token)
    if not new_refresh_token:
        body["refresh_token"] = fallback.refresh_token
        body["refresh_expires_in"] = fallback.refresh_expires_in
    elif body.get("refresh_expires_in") is None:
        body["refresh_expires_in"] = fallback.refresh_expires_in
    try:
        return OAuthToken.parse_obj(body), refresh_rotated
    except ValidationError as e:  # 2xx JSON missing the expected token fields
        raise AuthenticationError(
            f"Token endpoint {oauth_token_url} returned an unexpected response: {e}"
        ) from e


async def get_access_token_client_credentials(
    session: httpx.AsyncClient,
    oauth_token_url: str,
    client_id: str,
    client_secret: str,
    audience: str | None = None,
    scope: str = "openid",
) -> OAuthToken:
    """Obtain an access token via the OAuth2 client_credentials grant (RFC 6749 §4.4).

    Intended for confidential clients (server-to-server). Responses for this
    grant type typically do NOT include a refresh token (RFC 6749 §4.4.3 says
    SHOULD NOT). Empty values are backfilled so the OAuthToken schema (which
    requires both fields) still parses; the caller treats ``refresh_token=""``
    and ``refresh_expires_in=0`` as "no refresh available" and re-authenticates
    on each access-token expiry.

    Args:
        session: An ``httpx.AsyncClient`` (or compatible) used for the HTTP request.
        oauth_token_url: The token endpoint URL of the authorization server.
        client_id: The OAuth2 client identifier registered with the IdP.
        client_secret: The client secret for authenticating the request.
        audience: Optional audience string required by some IdPs (e.g. Auth0).
            Omit for IdPs that do not accept this parameter (e.g. Keycloak).
        scope: Space-separated OAuth2 scopes to request. Defaults to ``"openid"``.

    Returns:
        An ``OAuthToken`` containing the access token
        and related metadata. ``refresh_token`` is ``""`` and
        ``refresh_expires_in`` is ``0`` when the IdP did not issue a refresh token.

    Raises:
        AuthenticationError: If the token endpoint returns a non-2xx response.
    """
    logger.debug(
        f"get_access_token (client_credentials) from {oauth_token_url} using client_id: {client_id}"
    )
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
        "scope": scope,
    }
    if audience:
        payload["audience"] = audience
    body = await _post_token(session, oauth_token_url, payload)
    # Treat missing OR explicit-null refresh fields as 'no refresh available'.
    body["refresh_token"] = body.get("refresh_token") or ""
    body["refresh_expires_in"] = body.get("refresh_expires_in") or 0
    return OAuthToken.parse_obj(body)


_DISCOVERY_CACHE: dict[str, str] = {}


def clear_discovery_cache() -> None:
    """Clear the OIDC discovery cache. Useful for tests and for long-running
    processes that need to pick up an IdP configuration change without a restart."""
    _DISCOVERY_CACHE.clear()


async def discover_token_endpoint(session: httpx.AsyncClient, issuer: str) -> str:
    """Fetch the OIDC discovery document and return the token endpoint URL.

    Fetches ``{issuer}/.well-known/openid-configuration`` and extracts
    ``token_endpoint``. Results are cached per-issuer for the process
    lifetime; call ``clear_discovery_cache()`` to invalidate.

    The cache key is ``issuer.rstrip('/')`` so values differing only by a
    trailing slash share one cache entry. The same normalization is applied
    when comparing the returned ``issuer`` claim to the expected value.

    Per OIDC Discovery 1.0 §4.3, the ``issuer`` field in the discovery
    document MUST match the URL used to fetch it; a mismatch raises
    ``AuthenticationError`` to prevent credential redirection to a
    foreign token endpoint.

    Args:
        session: An ``httpx.AsyncClient`` (or compatible) used for the HTTP request.
        issuer: The base URL of the OpenID Provider (e.g.
            ``https://auth.example.com/realms/my-realm``). A trailing slash
            is accepted and normalized away.

    Returns:
        The ``token_endpoint`` URL string from the discovery document.

    Raises:
        AuthenticationError: If the discovery request fails, the response is
            not valid JSON, the JSON is not an object, the ``issuer`` claim
            does not match the expected value, or ``token_endpoint`` is
            absent or not a string.
    """
    key = issuer.rstrip("/")
    if key in _DISCOVERY_CACHE:
        return _DISCOVERY_CACHE[key]
    discovery_url = f"{key}/.well-known/openid-configuration"
    try:
        response = await session.get(discovery_url)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise AuthenticationError(f"OIDC discovery failed for {issuer}: {e}") from e
    try:
        body = response.json()
    except ValueError as e:
        raise AuthenticationError(
            f"OIDC discovery document at {discovery_url} is not valid JSON"
        ) from e
    if not isinstance(body, dict):
        raise AuthenticationError(
            f"OIDC discovery document at {discovery_url} is not a JSON object"
        )
    returned_issuer = body.get("issuer")
    if not isinstance(returned_issuer, str) or returned_issuer.rstrip("/") != key:
        raise AuthenticationError(
            f"OIDC discovery document at {discovery_url} returned issuer "
            f"{returned_issuer!r} which does not match the expected issuer {issuer!r}"
        )
    if "token_endpoint" not in body:
        raise AuthenticationError(
            f"OIDC discovery document at {discovery_url} is missing 'token_endpoint'"
        )
    token_endpoint = body["token_endpoint"]
    if not isinstance(token_endpoint, str):
        raise AuthenticationError(
            f"OIDC discovery document at {discovery_url} has a non-string 'token_endpoint': {token_endpoint!r}"
        )
    _DISCOVERY_CACHE[key] = token_endpoint
    return token_endpoint
