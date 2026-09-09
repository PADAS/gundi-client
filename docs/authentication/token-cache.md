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
| `file:///absolute/dir` | One private file per credential set (0600 files in a directory dedicated to the cache; created 0700, never re-moded if it already exists) | Local runs, scripts, hosts without Redis |
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
id, username, audience, scope, and, for the client-credentials grant, the client
secret. Two clients share a token exactly when all of those match. Rotating a
client secret produces a new key, so a token minted under the old secret is never
reused. A password is never part of the key: hashed next to guessable material it
would let anyone who can list the cache's keys brute-force it offline, and
changing a password does not invalidate tokens already issued. The username is
always in the key: a CLI profile client carries a username and a restored token
but no password, and several such clients under one client id must never share
an entry. (Replicas share only when their settings are identical, so an
incidental `GUNDI_USERNAME` on one replica keys it apart from the others.)

In Redis, entries expire with the later of the access-token and refresh-token
lifetimes. When the API answers with its login redirect (the response it gives
a token it no longer accepts), when it answers a plain `401`, or when a caller
passes `force_refresh_token=True`,
the rejected token is evicted from every layer before the client re-authenticates,
so no other replica keeps serving it. A client whose sibling, in this process or
another, has already replaced the rejected token adopts the replacement instead of
evicting it; a client that holds no token of its own always goes to the IdP, so
`gundi auth login` really validates the typed credentials. If the backend is
unreachable, the forced refresh still sees what siblings in the same process
wrote. When the IdP answers the refresh grant with `invalid_grant` (400 on
Keycloak, 403 on Auth0), or with a bare 400 carrying no error code, and the full
authentication also fails, the shared entry is dropped and this client stops
trying that refresh token; any other status, whatever its body says, leaves the
refresh token in place, since it may still be good. A transport failure on the
refresh grant (`AuthenticationError.transport`) is raised at once rather than
retried with the full authentication on the same broken network; a malformed
response body is not a transport failure and falls back like any other error. A forced refresh that fails for any
reason, network failures included, leaves the instance with no token, so its
next call goes to the IdP rather than serving the rejected one.
Token-endpoint failures of every kind surface as `AuthenticationError`, which
carries the HTTP status and the OAuth error code when there was a response.

### A token rejected with a plain `401`

The cache judges a token live by its expiry alone, so a token the IdP
invalidated early — a realm key rotation, an admin revoke-all, a client secret
rotated with immediate revocation — is not expired. Until 3.7.1 only the login
redirect evicted it, so if the API answered such a token with a plain `401`
instead, every client sharing the cache adopted the dead token and failed for
the rest of its access-token lifetime. A `401` now replaces the token and
retries, once per request.

If the API rejects *every* token, because the client has lost a role or the API
itself is broken, replacing on each request would cost one token request per
API request, per replica, where sharing the cache had made it roughly one
request per token lifetime. So a `401` on the token the last replacement
produced is reported as it stands for up to
`token_cache.REPLACEMENT_RETRY_COOLDOWN_SECONDS`. That throttle keys on *which*
token was rejected rather than on how recently any replacement happened: a
caller holding some older token is always allowed to ask, because a sibling
that has already fetched a replacement heals it for free, with no token
request. The window lapses, so a token minted before a fault was fixed is
retried rather than leaving the process stuck on it.

The record is kept per credential identity, the same identity the cache entry
is keyed by, so clients with unrelated credentials cannot clear each other's
and re-arm the throttle between them. Records past the cooldown are pruned as
new ones are written, and a cap bounds the rest, so a process cycling through
many identities does not accumulate one for each for ever.

The decision reads the token each request actually sent, not whatever the
client holds by the time the response arrives. Two requests in flight can both
carry the token the API rejects; the one whose response is examined second
retries with the replacement the first installed, rather than reading that
replacement as having been rejected in turn.

## Security

Access tokens are bearer credentials. Point the Redis backend at a database that
is as protected as the rest of your service's Redis data, and treat the file
backend's directory as you would a credentials file, and give the cache a
directory of its own: the cache creates it 0700 but never changes the mode of a
directory that already exists (it warns once if that directory is wider than
0700). A client secret enters the cache key only inside a one-way hash; a
password never enters it.

## Example

```python
from gundi_client_v2 import GundiClient

# All three share one token: same credentials, same process.
a = GundiClient()
b = GundiClient()
c = GundiClient(token_cache_url="redis://redis:6379/2")  # and with other replicas
```
