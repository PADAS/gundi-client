import logging

import httpx
from gundi_core.schemas import OAuthToken

from .errors import AuthenticationError

logger = logging.getLogger(__name__)

def _extract_oauth_error(response):
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


async def _post_token(session, oauth_token_url, payload) -> dict:
    """POST to the token endpoint; raise AuthenticationError on non-2xx."""
    response = await session.post(oauth_token_url, data=payload)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise AuthenticationError(_extract_oauth_error(e.response)) from e
    return response.json()


async def _token_request(session, oauth_token_url, payload) -> OAuthToken:
    return OAuthToken.parse_obj(await _post_token(session, oauth_token_url, payload))


# NOTE: The Resource Owner Password Credentials (ROPC) grant is discouraged by OAuth 2.1
# (RFC 9700). It is supported here intentionally, for public clients that require it.
async def get_access_token_password_grant(session, oauth_token_url, client_id, username, password, audience=None, scope="openid"):
    logger.debug(f"get_access_token (password grant) from {oauth_token_url} for user: {username}")
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
    session,
    oauth_token_url,
    client_id,
    refresh_token,
    fallback: OAuthToken,
    client_secret=None,
    scope="openid",
):
    """Exchange a refresh_token for a new access token (RFC 6749 §6).

    Returns a tuple ``(token, refresh_rotated)``. ``refresh_rotated`` is True
    when the IdP issued a new refresh_token in the response and False when it
    omitted one (RFC 6749 §6 makes the new refresh_token OPTIONAL). When the
    server omits it the cached refresh_token/refresh_expires_in from
    ``fallback`` are reused so the caller can keep its existing refresh
    metadata and the user's credentials are not re-transmitted.
    """
    logger.debug(f"refresh_access_token from {oauth_token_url} using client_id: {client_id}")
    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": scope,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    body = await _post_token(session, oauth_token_url, payload)
    refresh_rotated = "refresh_token" in body
    # Backfill missing refresh fields before constructing OAuthToken (which requires them).
    body.setdefault("refresh_token", fallback.refresh_token)
    body.setdefault("refresh_expires_in", fallback.refresh_expires_in)
    return OAuthToken.parse_obj(body), refresh_rotated


async def get_access_token_client_credentials(
    session,
    oauth_token_url,
    client_id,
    client_secret,
    audience=None,
    scope="openid",
):
    """Standard OAuth2 client_credentials grant (RFC 6749 §4.4) for confidential clients.

    Responses for client_credentials typically do NOT include a refresh_token
    (RFC 6749 §4.4.3 says SHOULD NOT). We backfill empty values so the OAuthToken
    schema (which requires both fields) still parses; the client orchestrator
    treats the empty refresh_token + refresh_expires_in=0 as 'no refresh available'
    and re-authenticates on each access-token expiry.
    """
    logger.debug(f"get_access_token (client_credentials) from {oauth_token_url} using client_id: {client_id}")
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


async def discover_token_endpoint(session, issuer: str) -> str:
    """Fetch the OIDC discovery document at ``{issuer}/.well-known/openid-configuration``
    and return its ``token_endpoint``. Cached per-issuer for the process lifetime;
    call :func:`clear_discovery_cache` to invalidate.

    The cache key is ``issuer.rstrip('/')`` so values differing only by a trailing
    slash share one cache entry.
    """
    key = issuer.rstrip("/")
    if key in _DISCOVERY_CACHE:
        return _DISCOVERY_CACHE[key]
    discovery_url = f"{key}/.well-known/openid-configuration"
    try:
        response = await session.get(discovery_url)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise AuthenticationError(
            f"OIDC discovery failed for {issuer}: {e}"
        ) from e
    try:
        token_endpoint = response.json()["token_endpoint"]
    except (ValueError, KeyError, TypeError) as e:
        raise AuthenticationError(
            f"OIDC discovery document at {discovery_url} is missing 'token_endpoint'"
        ) from e
    if not isinstance(token_endpoint, str):
        raise AuthenticationError(
            f"OIDC discovery document at {discovery_url} has a non-string 'token_endpoint': {token_endpoint!r}"
        )
    _DISCOVERY_CACHE[key] = token_endpoint
    return token_endpoint
