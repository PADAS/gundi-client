import logging
from gundi_core.schemas import (
    OAuthToken,
)

logger = logging.getLogger(__name__)


async def get_access_token(session, oauth_token_url, client_id, client_secret, audience):
    logger.debug(
        f"get_access_token from {oauth_token_url} using client_id: {client_id}"
    )
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "audience": audience,
        "grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
        "scope": "openid",
    }
    response = await session.post(oauth_token_url, data=payload)
    response.raise_for_status()
    token = response.json()
    return OAuthToken.parse_obj(token)


async def get_access_token_password_grant(session, oauth_token_url, client_id, username, password, audience):
    logger.debug(
        f"get_access_token (password grant) from {oauth_token_url} for user: {username}"
    )
    payload = {
        "client_id": client_id,
        "username": username,
        "password": password,
        "audience": audience,
        "grant_type": "password",
        "scope": "openid",
    }
    response = await session.post(oauth_token_url, data=payload)
    response.raise_for_status()
    token = response.json()
    return OAuthToken.parse_obj(token)
