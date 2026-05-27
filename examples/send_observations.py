"""
Example: Authenticate with username/password, get an integration's API key by name,
then use GundiDataSenderClient to send observations to Gundi.

Set credentials via environment variables (recommended) or pass them in code.
Required: GUNDI_USERNAME, GUNDI_PASSWORD, GUNDI_INTEGRATION_NAME
Optional: OAUTH_ISSUER (or OAUTH_TOKEN_URL), OAUTH_CLIENT_ID, OAUTH_AUDIENCE,
          GUNDI_API_BASE_URL, SENSORS_API_BASE_URL
"""

import asyncio
import os
from datetime import datetime, timezone

from gundi_client_v2 import GundiClient, GundiDataSenderClient


def get_client_kwargs():
    """Build GundiClient kwargs from environment."""
    username = os.environ.get("GUNDI_USERNAME")
    password = os.environ.get("GUNDI_PASSWORD")
    if not username or not password:
        raise ValueError(
            "Set GUNDI_USERNAME and GUNDI_PASSWORD in the environment, or pass them in code."
        )
    kwargs = {"username": username, "password": password}
    if os.environ.get("OAUTH_TOKEN_URL"):
        kwargs["oauth_token_url"] = os.environ["OAUTH_TOKEN_URL"]
    elif os.environ.get("OAUTH_ISSUER"):
        kwargs["oauth_token_url"] = (
            f"{os.environ['OAUTH_ISSUER'].rstrip('/')}/protocol/openid-connect/token"
        )
    if os.environ.get("OAUTH_CLIENT_ID"):
        kwargs["oauth_client_id"] = os.environ["OAUTH_CLIENT_ID"]
    if os.environ.get("OAUTH_AUDIENCE"):
        kwargs["oauth_audience"] = os.environ["OAUTH_AUDIENCE"]
    if os.environ.get("GUNDI_API_BASE_URL"):
        kwargs["base_url"] = os.environ["GUNDI_API_BASE_URL"]
    return kwargs


def get_sender_kwargs():
    """Build GundiDataSenderClient kwargs from environment (optional base URL)."""
    kwargs = {}
    if os.environ.get("SENSORS_API_BASE_URL"):
        kwargs["sensors_api_base_url"] = os.environ["SENSORS_API_BASE_URL"]
    return kwargs


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
        if not integration:
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
