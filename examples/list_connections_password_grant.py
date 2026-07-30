"""
Example: list Gundi connections using the OAuth2 password grant
(public client / user-facing developer auth).

# Required env vars:
#   GUNDI_API_BASE_URL, GUNDI_OAUTH_CLIENT_ID,
#   GUNDI_USERNAME, GUNDI_PASSWORD,
#   GUNDI_OAUTH_TOKEN_URL
# Conditional:
#   GUNDI_OAUTH_AUDIENCE  — required by some IdPs (e.g. Auth0 won't issue a usable
#                     API access token without it); ignored by Keycloak.

Run from the examples/ directory (so the local .env is loaded):

    cd examples
    python list_connections_password_grant.py
"""

import asyncio
import json
import os

from gundi_client_v2 import GundiClient


def _get_kwargs() -> dict:
    """Validate required env vars; raise ValueError listing any that are missing."""
    missing = []
    kwargs = {}

    if base_url := os.environ.get("GUNDI_API_BASE_URL"):
        kwargs["base_url"] = base_url
    else:
        missing.append("GUNDI_API_BASE_URL")

    if client_id := os.environ.get("GUNDI_OAUTH_CLIENT_ID"):
        kwargs["oauth_client_id"] = client_id
    else:
        missing.append("GUNDI_OAUTH_CLIENT_ID")

    if username := os.environ.get("GUNDI_USERNAME"):
        kwargs["username"] = username
    else:
        missing.append("GUNDI_USERNAME")

    if password := os.environ.get("GUNDI_PASSWORD"):
        kwargs["password"] = password
    else:
        missing.append("GUNDI_PASSWORD")

    if token_url := os.environ.get("GUNDI_OAUTH_TOKEN_URL"):
        kwargs["oauth_token_url"] = token_url
    else:
        missing.append("GUNDI_OAUTH_TOKEN_URL")

    # Conditional — sent to the token endpoint when set; some IdPs require it.
    if audience := os.environ.get("GUNDI_OAUTH_AUDIENCE"):
        kwargs["oauth_audience"] = audience

    if missing:
        raise ValueError(f"Missing required env vars: {', '.join(missing)}")
    return kwargs


async def main():
    async with GundiClient(**_get_kwargs()) as client:
        # `params` is forwarded to the underlying GET. The Gundi API supports
        # several server-side filters on this endpoint:
        #   status:        "healthy" | "unhealthy" | "disabled" | "needs_review"
        #   provider_type: e.g. "earth_ranger", "traptagger"
        #   destination_type, destination_url, destination_id (UUID), source_id (UUID), owner
        # Results are paginated (default PAGE_SIZE=20); get_connections returns
        # only the first page as a list.
        connections = await client.get_connections(params={"status": "healthy"})
        # `default=str` renders UUIDs and datetimes as their canonical string
        # forms so json.dumps can serialize them. Output is pure JSON — pipe to
        # `jq` for filtering: `python list_connections_password_grant.py | jq '.[].provider.name'`
        print(json.dumps([c.dict() for c in connections], default=str, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
