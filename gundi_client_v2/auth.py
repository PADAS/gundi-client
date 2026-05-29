import logging

import httpx
from gundi_core.schemas import OAuthToken

from .errors import AuthenticationError

logger = logging.getLogger(__name__)

UMA_TICKET_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:uma-ticket"


def _extract_oauth_error(response):
    """Build a detail string from an RFC 6749 §5.2 token-error response."""
    status = response.status_code
    try:
        body = response.json()
    except ValueError:
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


async def get_access_token(session, oauth_token_url, client_id, client_secret, audience=None, scope="openid"):
    logger.debug(f"get_access_token from {oauth_token_url} using client_id: {client_id}")
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": UMA_TICKET_GRANT_TYPE,
        "scope": scope,
    }
    if audience:
        payload["audience"] = audience
    return await _token_request(session, oauth_token_url, payload)


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
