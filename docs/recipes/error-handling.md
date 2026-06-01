# Error handling

`gundi_client_v2` raises a small, consistent exception hierarchy. Every
error the library surfaces is a subclass of `GundiClientError`.

## The exception hierarchy

```
GundiClientError
  ├── AuthenticationError       # OAuth/token failures
  └── GundiAPIError             # 4xx/5xx HTTP responses
```

- `AuthenticationError` — raised when the OAuth token request fails (bad
  credentials, unreachable IdP, misconfigured issuer URL, etc.).
- `GundiAPIError` — raised when the Gundi API returns a 4xx or 5xx
  response. Exposes `.status_code: int` and `.detail: str`.

## Catching by category

```python
import asyncio
from gundi_client_v2 import GundiClient
from gundi_client_v2.errors import (
    AuthenticationError,
    GundiAPIError,
    GundiClientError,
)


async def main():
    try:
        async with GundiClient() as client:
            connections = await client.get_connections()
    except AuthenticationError as e:
        # Token request failed; check credentials or client configuration
        print(f"Auth error: {e}")
    except GundiAPIError as e:
        # 4xx/5xx from the Gundi API
        print(f"Status {e.status_code}, detail: {e.detail}")
    except GundiClientError as e:
        # Anything else from the library (rare)
        print(f"Client error: {e}")


asyncio.run(main())
```

Catch the most specific exception first (`AuthenticationError`,
`GundiAPIError`), then `GundiClientError` as a catch-all for anything
unexpected from the library.

## Handling specific status codes

`GundiAPIError.status_code` lets you branch on the HTTP status:

```python
except GundiAPIError as e:
    if e.status_code == 404:
        # Resource doesn't exist (or you don't have access)
        ...
    elif e.status_code == 403:
        # Permission denied
        ...
    elif e.status_code >= 500:
        # Server-side issue; consider retrying
        ...
```

`GundiAPIError.detail` contains the body text returned by the API,
which typically has a human-readable description of the problem.

## Logging useful context

Log `status_code` and `detail` alongside the operation that failed:

```python
import logging

logger = logging.getLogger(__name__)


async def fetch_integration(client, integration_id):
    try:
        return await client.get_integration_details(integration_id)
    except GundiAPIError as e:
        logger.error(
            "Failed to fetch integration",
            extra={
                "integration_id": integration_id,
                "status_code": e.status_code,
                "detail": e.detail,
            },
        )
        raise
```

Re-raising preserves the original traceback for upstream handlers or
monitoring tools.

## Retry strategies

For transient errors (5xx responses, network blips), retry only on
those — not on 4xx errors that won't resolve on a second attempt. The
[`stamina`](https://pypi.org/project/stamina/) library provides
exponential back-off with jitter and accepts a **predicate** for the
`on=` parameter to filter which exceptions trigger a retry:

First install stamina (`pip install stamina`):

```python
import stamina
from gundi_client_v2 import GundiClient
from gundi_client_v2.errors import GundiAPIError


def _is_transient(exc: BaseException) -> bool:
    """Retry only on 5xx server errors."""
    return isinstance(exc, GundiAPIError) and exc.status_code >= 500


@stamina.retry(on=_is_transient, attempts=3)
async def list_connections(client: GundiClient) -> list:
    return await client.get_connections()


async def main():
    async with GundiClient() as client:
        connections = await list_connections(client)
```

Be selective about what you retry:

- **Do retry:** 5xx server errors — they indicate a transient server-side
  problem that may resolve on the next attempt.
- **Do not retry:** 4xx errors — they indicate a client-side problem
  (bad request, wrong ID, missing permission) that won't resolve by
  retrying. The predicate above ignores them.

## Related pages

- [Authentication: Refresh and errors](../authentication/refresh-and-errors.md)
- [Troubleshooting](../troubleshooting.md)
