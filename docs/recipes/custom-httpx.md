# Custom HTTPX client

`GundiClient` builds and owns its HTTPX session internally. You cannot
pass a pre-built `httpx.AsyncClient` instance, but several constructor
kwargs let you tune the session's behavior.

## Timeouts

Two separate timeout knobs control how long the client waits:

- `connect_timeout` — TCP connect timeout (default: **3.1 seconds**)
- `data_timeout` — read/write timeout per request (default: **20 seconds**)

```python
from gundi_client_v2 import GundiClient

client = GundiClient(
    connect_timeout=10.0,
    data_timeout=60.0,
)
```

Increase `data_timeout` if you're hitting timeouts on large read
operations against a slow deployment. Increase `connect_timeout` if
you're on a high-latency network.

## Retries

`max_http_retries` sets the number of transport-layer connection retries
(default: **5**):

```python
client = GundiClient(
    max_http_retries=3,
)
```

These are TCP-level retries handled by `httpx.AsyncHTTPTransport`, not
application-level retries for 4xx/5xx HTTP responses. For retrying on
HTTP errors, use a library like `stamina` — see
[Error handling](error-handling.md).

## SSL verification

`use_ssl` controls certificate verification (default: **True**):

```python
client = GundiClient(
    use_ssl=False,
)
```

**Only disable this for local development** against a self-signed IdP or
a test environment without valid certificates. Never set `use_ssl=False`
in production.

## Combining options

All kwargs can be passed in the same constructor call:

```python
async with GundiClient(
    connect_timeout=10.0,
    data_timeout=60.0,
    max_http_retries=3,
) as client:
    connections = await client.get_connections()
```

## What you cannot customize

There is no kwarg to:

- Pass a pre-built `httpx.AsyncClient` instance
- Supply a custom HTTPX transport (e.g. a proxy transport)
- Set a proxy URL

If you need any of these, open an issue at
[github.com/PADAS/gundi-client/issues](https://github.com/PADAS/gundi-client/issues).

## Related pages

- [Troubleshooting](../troubleshooting.md)
- [Error handling](error-handling.md)
