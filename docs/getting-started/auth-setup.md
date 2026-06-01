# Authentication setup

`gundi-client-v2` reads its OAuth2 configuration from environment variables
by default. This page covers the **happy path** for most users; for
detailed coverage of each grant type, see the
[Authentication section](../authentication/overview.md).

## What you need from your Gundi administrator

- The **API base URL** for your Gundi deployment (e.g.
  `https://api.gundiservice.org`).
- An **OAuth issuer URL** for the IdP behind Gundi
  (e.g. `https://auth.gundiservice.org/realms/your-realm`).
- An **OAuth client** (ID, and a secret if it's a confidential client).
- Either user credentials (for password grant) **or** a client secret
  (for client_credentials).

## Choose a grant type

| Use this | When |
|---|---|
| `client_credentials` | Server-to-server, no user identity involved. Your client is confidential (has a secret). |
| `password` | Acting on behalf of a known user with their credentials. Your client is public (no secret). |

If unsure, ask your Gundi administrator which grant your client is configured
for.

## Set the environment variables

Create a `.env` file next to your application code, or export these in your
shell:

=== "client_credentials"

    ```env
    GUNDI_API_BASE_URL=https://api.gundiservice.org
    OAUTH_ISSUER=https://auth.gundiservice.org/realms/your-realm
    OAUTH_CLIENT_ID=your-client-id
    OAUTH_CLIENT_SECRET=your-client-secret
    # OAUTH_AUDIENCE=your-api-audience   # required by some IdPs (e.g. Auth0)
    ```

=== "password grant"

    ```env
    GUNDI_API_BASE_URL=https://api.gundiservice.org
    OAUTH_ISSUER=https://auth.gundiservice.org/realms/your-realm
    OAUTH_CLIENT_ID=your-client-id
    GUNDI_USERNAME=your-username
    GUNDI_PASSWORD=your-password
    # OAUTH_AUDIENCE=your-api-audience   # required by some IdPs (e.g. Auth0)
    ```

## How the library uses these

When you create a `GundiClient()` with no arguments, it reads these env vars
through `gundi_client_v2.settings`. Setting `OAUTH_ISSUER` triggers **OIDC
discovery**: the library fetches the IdP's
`/.well-known/openid-configuration` document on the first auth attempt and
caches the resolved token endpoint for the process lifetime.

If your IdP doesn't expose discovery, set `OAUTH_TOKEN_URL` directly instead
of `OAUTH_ISSUER`.

!!! tip "Audience parameter"
    `OAUTH_AUDIENCE` is required by some IdPs (notably Auth0 won't issue a
    usable API access token without it) and ignored by others (Keycloak
    password grant). Set it if your IdP requires it; leave it unset
    otherwise.

## Loading the `.env` file

The library calls `environs.Env.read_env()` at import time. By default this
reads `./.env` from the current working directory. Run your script from the
directory containing `.env`, or set `GUNDI_CLIENT_ENVFILE=/path/to/your.env`
to point at a specific file.

## Next

→ [First request](first-request.md) — list the Connections in your account
to verify everything works.
