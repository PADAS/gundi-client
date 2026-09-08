# Shared token cache

Every `GundiClient` shares one OAuth token per set of credentials.

## Why

Without a shared cache, each `GundiClient` instance requests its own token and
forgets it when the instance goes away. Services that build a client per call
mint a new Keycloak token for nearly every request, although the token would be
valid for hours or days. The cache keeps that token and hands it to every client
that has the same credentials, for as long as it is valid.

## Layers

**Process memory (always on).** Every client in a process reads and writes one
in-memory table keyed by credentials. Concurrent clients that miss at the same
moment wait for one token request instead of each making their own. Nothing to
configure. `gundi_client_v2.token_cache.clear_token_cache()` empties it (tests,
or a long-running process that must drop every cached token).

**One durable backend (optional).** Chosen by `GUNDI_TOKEN_CACHE_URL` or the
`token_cache_url=` kwarg:

| URL | Backend | Use it for |
|---|---|---|
| `redis://host:port/db`, `rediss://…` | Redis (`pip install gundi-client-v2[redis]`) | Several replicas or processes sharing one Redis |
| `file:///absolute/dir` | One private file per credential set (0700 dir, 0600 files) | Local runs, scripts, hosts without Redis |
| unset | none | Tokens shared within the process only |

`token_cache=` accepts any object with async `get(key)`, `set(key, token)` and
`delete(key)` and takes precedence over the URL.

The file backend is for local disk only: it does blocking file I/O on the event
loop, so a network filesystem (NFS, SMB, a mounted bucket) is not a supported
target; point those deployments at Redis.

There is no fallback chain. When the backend is unreachable the client logs one
warning per outage and runs on the memory layer until it recovers; the cache
never raises into an API call. A bad URL, or `redis://` without the `redis`
package, raises `TokenCacheConfigError` when the client is constructed. A Redis
backend built from a URL is memoized per process and its connection pool is
bound to the event loop that first used it, so a process that runs more than one
event loop over its life degrades to the memory layer, with one warning, on the
other loops.

## What is shared, and with whom

The cache key is a SHA-256 over the resolved token endpoint, grant type, client
id, username (password grant), audience, scope, and the secret. Two clients
share a token exactly when all of those match. Rotating a secret produces a new
key, so a token minted under the old secret is never reused. The key reveals
nothing about the credentials.

In Redis, entries expire with the later of the access-token and refresh-token
lifetimes. When the API answers with its login redirect (the response it gives
a token it no longer accepts), or when a caller passes `force_refresh_token=True`,
the entry is evicted from every layer before the client re-authenticates, so no
other replica keeps serving it.

## Security

Access tokens are bearer credentials. Point the Redis backend at a database that
is as protected as the rest of your service's Redis data, and treat the file
backend's directory as you would a credentials file. The secret itself never
leaves the process; it enters the cache key only inside a one-way hash.

## Example

```python
from gundi_client_v2 import GundiClient

# All three share one token: same credentials, same process.
a = GundiClient()
b = GundiClient()
c = GundiClient(token_cache_url="redis://redis:6379/2")  # and with other replicas
```
