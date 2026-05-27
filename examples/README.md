# Gundi Client examples

Simple examples for using the Gundi client with **username and password** credentials to access Gundi's API.

## Setup

From the repository root, install the package in editable mode:

```bash
pip install -e .
```

Then set the required environment variables (or pass credentials in code where the example allows it). You can copy `examples/.env.example` to `examples/.env` and fill in your values; the client will load `.env` from the current directory when run.

## Examples

### send_observations.py

Demonstrates:

1. Authenticating with a username and password
2. Querying for integrations
3. Selecting one integration by name and fetching its API key
4. Using `GundiDataSenderClient` with that API key to send observations to Gundi

**Required environment variables:**

- `GUNDI_USERNAME` – your Gundi username
- `GUNDI_PASSWORD` – your Gundi password
- `GUNDI_INTEGRATION_NAME` – exact name of the integration to use for sending (e.g. the display name in the portal)

**Optional (OAuth / API endpoints):**

- `OAUTH_ISSUER` – OAuth issuer base URL (e.g. `https://auth.example.com/auth/realms/my-realm`); token URL is derived as `{OAUTH_ISSUER}/protocol/openid-connect/token`
- `OAUTH_TOKEN_URL` – full OAuth token URL (overrides `OAUTH_ISSUER` if set)
- `OAUTH_CLIENT_ID` – OAuth client id for the password grant
- `OAUTH_AUDIENCE` – OAuth audience
- `GUNDI_API_BASE_URL` – Gundi API base URL (portal/configuration API)
- `SENSORS_API_BASE_URL` – Sensors/ingestion API base URL (used by `GundiDataSenderClient`)

**Run:**

```bash
python examples/send_observations.py
```

Ensure the integration named in `GUNDI_INTEGRATION_NAME` exists in your Gundi deployment and has an API key configured.
