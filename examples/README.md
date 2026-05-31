# Gundi Client examples

Simple examples for using the Gundi client with **username and password** credentials to access Gundi's API.

## Setup

From the repository root, install the package in editable mode:

```bash
pip install -e .
```

Then set the required environment variables (or pass credentials in code where the example allows it).

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
- `OAUTH_CLIENT_ID` – OAuth client ID for the password grant
- `GUNDI_API_BASE_URL` – Gundi API base URL (portal/configuration API)
- `SENSORS_API_BASE_URL` – Sensors/ingestion API base URL (used by `GundiDataSenderClient`)
- At least one of:
  - `OAUTH_ISSUER` – OIDC issuer base URL (e.g. `https://auth.example.com/realms/my-realm`); the token endpoint is discovered automatically via `{OAUTH_ISSUER}/.well-known/openid-configuration`.
  - `OAUTH_TOKEN_URL` – explicit OAuth token endpoint URL (overrides OIDC discovery when set).

**Conditional:**

- `OAUTH_AUDIENCE` – OAuth audience. Required by some IdPs (e.g., Auth0 needs it to issue a usable API access token); ignored by others (Keycloak password grant). Set if your IdP requires it.

**Optional:**

- `GUNDI_API_SSL_VERIFY` – set to `false` to skip SSL verification (default: `true`)

**Setting up credentials with a `.env` file:**

Copy `.env.example` to `.env` (in the `examples/` directory) and fill in your values:

```bash
cp examples/.env.example examples/.env
# edit examples/.env
```

The client loads `.env` from the **current working directory**, so run the script from the `examples/` directory:

```bash
cd examples
python send_observations.py
```

Alternatively, run from the repo root and point to the file explicitly:

```bash
GUNDI_CLIENT_ENVFILE=examples/.env python examples/send_observations.py
```

Ensure the integration named in `GUNDI_INTEGRATION_NAME` exists in your Gundi deployment and has an API key configured.

### Listing connections — three auth paths

These small scripts each list the Gundi connections accessible to the
configured client, demonstrating the three OAuth2 auth paths the library
supports. The library call is identical (`client.get_connections(...)`)
in all three — the variation is purely how the client is configured.

| Script | Auth path | Token URL source |
|---|---|---|
| `list_connections_client_credentials.py` | client_credentials grant (confidential client / M2M) | explicit `OAUTH_TOKEN_URL` |
| `list_connections_password_grant.py` | password grant (public client / user-facing) | explicit `OAUTH_TOKEN_URL` |
| `list_connections_discovery.py` | password grant + OIDC discovery (IdP-agnostic) | discovered from `OAUTH_ISSUER` — requires `gundi-client-v2 >= 2.6.0` |

All three run the same way as `send_observations.py`:

```bash
cd examples
python list_connections_<mode>.py
```

Each script also demonstrates passing `params={...}` to
`get_connections` for server-side filtering — see the Gundi API docs for
the available filter keys. The bundled example uses `params={"status": "healthy"}`.

The required env vars for each are listed in the script's module
docstring; `.env.example` also annotates which variables each example uses.
