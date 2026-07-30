# Refresh and errors

How the library reuses tokens, when it re-authenticates, and the errors
you'll see when something goes wrong.

## Token lifecycle inside `GundiClient`

The client caches the most recent `OAuthToken` in memory, along with two
computed timestamps:

- `expires_at` — when the access token will become invalid
- `refresh_expires_at` — when the refresh token will become invalid

Both have a small safety buffer (15 seconds) subtracted so the client treats
a token as expired slightly *before* the server does.

On every authenticated request, the client checks:

1. **Is the access token still valid?** → Use it.
2. **Is the refresh token still valid?** → Refresh and use the new access
   token (RFC 6749 §6).
3. **Otherwise** → Re-authenticate via the configured grant.

## Refresh token rotation

RFC 6749 §6 makes returning a new refresh token in the refresh response
**optional**. Two scenarios:

**Rotating IdP** (Keycloak default, most modern IdPs): every refresh
response includes a new `refresh_token` that replaces the previous one. The
client treats this as the canonical behavior and updates its cache.

**Non-rotating IdP**: the refresh response includes only a new access token,
no new refresh token. The client recognizes this case, keeps the existing
cached refresh token, and continues using it until the IdP rejects it.

You don't have to do anything to support either case — the library detects
which one your IdP is using.

## `client_credentials` re-authentication

`client_credentials` responses don't usually include a refresh token (per
RFC 6749 §4.4.3). The client treats these tokens as "no refresh available":
when they expire, it runs the `client_credentials` grant again. Because no
user credentials are involved, this is cheap.

## Common errors

### `Token request failed: HTTP 401 (invalid_client)`

The client ID or secret is wrong, or the client doesn't exist in the realm.

**Fix:** Verify `GUNDI_OAUTH_CLIENT_ID` and `GUNDI_OAUTH_CLIENT_SECRET`. For Keycloak,
also confirm the client is in the correct realm under `GUNDI_OAUTH_ISSUER`.

### `Token request failed: HTTP 401 (invalid_grant)`

The credentials don't match a user (password grant), or the refresh token
has been revoked or expired (refresh grant).

**Fix:** For password grant, verify `GUNDI_USERNAME` and `GUNDI_PASSWORD`.
For refresh grant, the client should fall back to a fresh password/client_
credentials grant automatically; if it doesn't, check that the fallback
credentials are still in the env.

### `Token request failed: HTTP 401 (unauthorized_client)`

The client isn't permitted to use this grant type at the IdP. Common in
Keycloak when "Direct Access Grants Enabled" (password grant) or "Service
Accounts Enabled" (client_credentials) hasn't been toggled on for the
client.

**Fix:** Ask your IdP administrator to enable the appropriate grant for the
client.

### `Token request failed: HTTP 400 (invalid_scope)`

The requested scope isn't allowed for this client.

**Fix:** Pass a `scope=...` kwarg to the grant function, or unset
`GUNDI_OAUTH_SCOPE` if you set it explicitly. The library's default scope is
`openid`.

### `AuthenticationError: OIDC discovery failed for ...`

See [OIDC discovery → Errors](oidc-discovery.md#errors).

## Handling auth errors in your code

`AuthenticationError` is a subclass of `gundi_client_v2.errors.GundiClientError`.
Catch it around your client calls if you want to handle expired credentials
gracefully:

```python
from gundi_client_v2 import GundiClient
from gundi_client_v2.errors import AuthenticationError


async def main():
    try:
        async with GundiClient() as client:
            connections = await client.get_connections()
    except AuthenticationError as e:
        print(f"Auth failed: {e}")
        # ... fetch new credentials, prompt user, exit, etc.
```

## See also

- [Overview](overview.md) for the grant-selection logic
- [Troubleshooting](../troubleshooting.md) for non-auth errors
