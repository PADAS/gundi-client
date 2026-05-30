"""
Example: Authenticate with username/password, get an integration's API key by name,
then use GundiDataSenderClient to send observations to Gundi.

Set credentials via environment variables (recommended) or pass them in code.

# Required (read by this script; one of OAUTH_ISSUER or OAUTH_TOKEN_URL must be set):
#   GUNDI_USERNAME, GUNDI_PASSWORD,
#   GUNDI_API_BASE_URL, SENSORS_API_BASE_URL,
#   OAUTH_CLIENT_ID, OAUTH_AUDIENCE,
#   OAUTH_ISSUER  (library derives the token URL as {issuer}/protocol/openid-connect/token)
#     OR
#   OAUTH_TOKEN_URL  (read by this script and passed as the oauth_token_url kwarg to GundiClient)
# Optional: OAUTH_AUDIENCE, GUNDI_API_SSL_VERIFY

Run from the examples/ directory (so the .env file in that directory is loaded):

    cd examples
    python send_observations.py

Or from the repo root using GUNDI_CLIENT_ENVFILE:

    GUNDI_CLIENT_ENVFILE=examples/.env python examples/send_observations.py
"""

import asyncio
import os
from datetime import datetime, timezone

from gundi_client_v2 import GundiClient, GundiDataSenderClient


def get_client_kwargs():
    """Build GundiClient kwargs from environment, validating required settings."""
    username = os.environ.get("GUNDI_USERNAME")
    password = os.environ.get("GUNDI_PASSWORD")
    if not username or not password:
        raise ValueError(
            "Set GUNDI_USERNAME and GUNDI_PASSWORD in the environment, or pass them in code."
        )

    oauth_client_id = os.environ.get("OAUTH_CLIENT_ID")
    oauth_token_url = os.environ.get("OAUTH_TOKEN_URL")
    oauth_issuer = os.environ.get("OAUTH_ISSUER")
    gundi_api_base_url = os.environ.get("GUNDI_API_BASE_URL")

    missing = []
    if not oauth_client_id:
        missing.append("OAUTH_CLIENT_ID")
    if not oauth_token_url and not oauth_issuer:
        missing.append("OAUTH_TOKEN_URL (or OAUTH_ISSUER)")
    if not gundi_api_base_url:
        missing.append("GUNDI_API_BASE_URL")
    if missing:
        raise ValueError(
            f"Missing required environment variable(s): {', '.join(missing)}"
        )

    kwargs = {"username": username, "password": password}
    if oauth_token_url:
        kwargs["oauth_token_url"] = oauth_token_url
    elif oauth_issuer:
        # Note: OAUTH_ISSUER must not have a trailing slash — the token URL is
        # derived by appending /protocol/openid-connect/token and the value is
        # not stripped.
        kwargs["oauth_token_url"] = (
            f"{oauth_issuer}/protocol/openid-connect/token"
        )
    kwargs["oauth_client_id"] = oauth_client_id
    kwargs["base_url"] = gundi_api_base_url
    if os.environ.get("OAUTH_AUDIENCE"):
        kwargs["oauth_audience"] = os.environ["OAUTH_AUDIENCE"]
    return kwargs


def get_sender_kwargs():
    """Build GundiDataSenderClient kwargs from environment, validating required settings."""
    sensors_api_base_url = os.environ.get("SENSORS_API_BASE_URL")
    if not sensors_api_base_url:
        raise ValueError(
            "Missing required environment variable: SENSORS_API_BASE_URL"
        )
    return {"sensors_api_base_url": sensors_api_base_url}


async def main():
    integration_name = os.environ.get("GUNDI_INTEGRATION_NAME")
    if not integration_name:
        raise ValueError(
            "Set GUNDI_INTEGRATION_NAME to the name of the integration to use for sending."
        )

    client_kwargs = get_client_kwargs()
    sender_kwargs = get_sender_kwargs()

    async with GundiClient(**client_kwargs) as client:
        # 1. Authenticate (implicit on first request) and query integrations
        integration = None
        names = []
        async for i in client.get_integrations():
            names.append(i.name)
            if i.name == integration_name:
                integration = i
                break
        if integration is None:
            raise ValueError(
                f"No integration named {integration_name!r}. Available: {names}"
            )

        # 2. Get the integration's API key
        api_key = await client.get_integration_api_key(integration.id)
        if not api_key:
            raise ValueError(
                f"Integration {integration_name!r} has no API key."
            )

    # 3. Send observations using GundiDataSenderClient
    sender = GundiDataSenderClient(
        integration_api_key=api_key,
        **sender_kwargs,
    )
    observations = [
        {
            "source": 2,
            "source_name": "Python example script",
            "type": "tracking-device",
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "location": {"lat": -12.398828, "lon": -74.263916},
            "additional": {"example": True},
        }
    ]
    response = await sender.post_observations(observations)
    print("Sent observations. Response:", response)


if __name__ == "__main__":
    asyncio.run(main())
