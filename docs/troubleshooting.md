# Troubleshooting

Common errors when using `gundi-client-v2`, with their causes and fixes.

## Authentication errors

See [Authentication → Refresh and errors](authentication/refresh-and-errors.md)
for the full catalog with explanations.

## `httpx.ConnectError: [Errno -2] Name or service not known`

The hostname in `GUNDI_API_BASE_URL` or `OAUTH_ISSUER` doesn't resolve.

**Fix:** Verify the URLs are correct and reachable from the host running
your code. Common gotchas:

- Typos in the host (`gundiservice.org` vs `gundiserice.org`)
- Missing `https://` scheme
- Internal hostnames that don't resolve outside a VPN

## `httpx.ConnectTimeout` or `httpx.ReadTimeout`

The server isn't responding within the configured timeout. The defaults are
3.1 seconds for `connect` and 20 seconds for `data` (read).

**Fix:** Increase timeouts at construction time using the
`connect_timeout` and `data_timeout` kwargs:

```python
from gundi_client_v2 import GundiClient

client = GundiClient(
    connect_timeout=60.0,  # seconds to establish the connection
    data_timeout=60.0,     # seconds to read the response body
)
```

## `TypeError: Client.__init__() got an unexpected keyword argument 'app'`

You're on `httpx>=0.28` but `starlette<0.37`. This usually surfaces in
FastAPI test code (`TestClient(app)`).

**Fix:** See [Migration → Troubleshooting](migration.md#troubleshooting).
Short version: bump `fastapi` to `>=0.110.3` (which allows
`starlette>=0.37`).

## `ValidationError` from Pydantic when parsing a response

The API returned a payload that doesn't match the expected `gundi-core`
schema. This typically happens during version skew (your client and the
server are out of sync) or for newly-introduced fields.

**Fix:**

- Confirm the deployed Gundi version matches your client major version.
- If the field is benign, you may need to upgrade `gundi-core` to a release
  that knows about it.
- If you suspect a server bug, capture the raw response by intercepting
  the HTTPX transport and report it to your Gundi administrator.

## `GundiAPIError: HTTP 403`

The authenticated principal doesn't have permission to access the
requested resource.

**Fix:** Check that your client/user has the necessary roles in the IdP
realm. For per-Integration resources, your principal must own or be
granted access to that Integration's Organization.

## `GundiAPIError: HTTP 404`

The resource doesn't exist or you don't have permission to see it (some
APIs return 404 instead of 403 to avoid leaking resource existence).

**Fix:** Verify the ID is correct. If you have an `integration_id` from
elsewhere, confirm it actually exists with
`client.get_integration_details(integration_id)`.

## Stuck?

- Check the [Authentication overview](authentication/overview.md) for
  grant-selection issues.
- Check the [Migration guide](migration.md) if you recently upgraded.
- Open an issue at
  [github.com/PADAS/gundi-client/issues](https://github.com/PADAS/gundi-client/issues).
