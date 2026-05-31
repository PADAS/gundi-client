"""
Example: list Gundi connections using the OAuth2 password grant with OIDC
discovery — the library finds the token endpoint at
{OAUTH_ISSUER}/.well-known/openid-configuration instead of needing
OAUTH_TOKEN_URL configured explicitly.

This is the IdP-agnostic path: it works against Keycloak, Auth0, Okta, and
any other OIDC-compliant IdP with no code change — only OAUTH_ISSUER
differs per deployment. After the Auth0 migration, point OAUTH_ISSUER at
the Auth0 tenant and this same script keeps working.

# Required env vars:
#   GUNDI_API_BASE_URL, OAUTH_CLIENT_ID,
#   GUNDI_USERNAME, GUNDI_PASSWORD,
#   OAUTH_ISSUER
# Conditional:
#   OAUTH_AUDIENCE  — required by some IdPs (e.g. Auth0 won't issue a usable
#                     API access token without it); ignored by Keycloak.

# Requires gundi-client-v2 >= 2.6.0 (OIDC discovery support).

# Performance: the first auth incurs one extra HTTP request (the discovery
# document); the resolved token endpoint is cached process-wide thereafter.
# Call gundi_client_v2.auth.clear_discovery_cache() to invalidate.

Run from the examples/ directory (so the local .env is loaded):

    cd examples
    python list_connections_discovery.py
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

    if client_id := os.environ.get("OAUTH_CLIENT_ID"):
        kwargs["oauth_client_id"] = client_id
    else:
        missing.append("OAUTH_CLIENT_ID")

    if username := os.environ.get("GUNDI_USERNAME"):
        kwargs["username"] = username
    else:
        missing.append("GUNDI_USERNAME")

    if password := os.environ.get("GUNDI_PASSWORD"):
        kwargs["password"] = password
    else:
        missing.append("GUNDI_PASSWORD")

    # NOTE: oauth_issuer (NOT oauth_token_url) — the library will resolve the
    # token endpoint via OIDC discovery at runtime.
    if issuer := os.environ.get("OAUTH_ISSUER"):
        kwargs["oauth_issuer"] = issuer
    else:
        missing.append("OAUTH_ISSUER")

    # Conditional — sent to the token endpoint when set; some IdPs require it.
    if audience := os.environ.get("OAUTH_AUDIENCE"):
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
        # `jq` for filtering: `python list_connections_discovery.py | jq '.[].provider.name'`
        print(json.dumps([c.dict() for c in connections], default=str, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
