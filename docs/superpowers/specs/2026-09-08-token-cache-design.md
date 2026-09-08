# Shared OAuth token cache for `GundiClient`

**Date:** 2026-09-08
**Status:** implemented on branch `cd/token-cache` (Part A); amended 2026-09-08 after the whole-branch review: `to_oauth_token` reports remaining lifetimes instead of zeros, `redis` extra pinned `<9`, per-key locks are bound to the running event loop
**Release:** gundi-client-v2 3.7.0

## Problem

Every `GundiClient` instance caches its OAuth token in memory and reuses it until
15 seconds before expiry (`get_access_token`, `_store_token`). The cache dies with
the instance. The action-runner template builds a new instance per portal call in
its send path (`app/services/gundi.py`, one client per batch of events or
observations forwarded) and its configuration-reload path
(`app/services/config_manager.py`), so a runner requests a new token from
Keycloak for nearly every interaction with the Gundi API. The dev Keycloak issues
those tokens with a 48-hour lifetime; almost every one is used once and
discarded. Every replica of every runner does this independently.

The goal is to mint as few Keycloak tokens as possible: one token per set of
credentials, shared by every client in a process and by every process that
shares a Redis, for as long as it is valid.

## Decisions taken during design

1. A process-wide in-memory layer is always on for every `GundiClient`. This is
   a behavior change for library consumers and is accepted.
2. Configuration by URL is the primary path (`GUNDI_TOKEN_CACHE_URL` env var,
   `token_cache_url=` kwarg). A `token_cache=` kwarg accepts an injected backend
   for callers that want to own the connection, and for tests.
3. One durable backend per process, chosen by the URL, with memory always in
   front. No fallback chain: when the backend is unavailable the client runs on
   memory alone and logs a warning. The file backend exists for processes
   without Redis (local runs, scripts), not as a fallback behind Redis.
4. The CLI keeps its own per-environment token store
   (`gundi_client_v2/cli/token_store.py`). Unifying it with this cache is a
   follow-up.
5. The runners do not get a new deployment variable: the template derives the
   URL from its existing `REDIS_HOST` and `REDIS_PORT` plus a new
   `REDIS_TOKEN_CACHE_DB` setting (default `2`, next to the state database at
   `0` and the config cache at `1`) and passes it through one client factory.

## Design

### Module `gundi_client_v2/token_cache.py`

```python
@dataclass(frozen=True)
class CachedToken:
    access_token: str
    refresh_token: str          # "" when the grant issued none
    token_type: str
    expires_at: datetime        # tz-aware, absolute
    refresh_expires_at: datetime  # tz-aware; datetime.min (UTC) when no refresh token

    def to_oauth_token(self, now=None) -> OAuthToken   # expires_in / refresh_expires_in = remaining seconds (0 once expired)
    def is_live(self, now) -> bool           # expires_at > now
    def refresh_is_live(self, now) -> bool   # refresh_token and refresh_expires_at > now

class TokenCache(Protocol):
    async def get(self, key: str) -> CachedToken | None: ...
    async def set(self, key: str, token: CachedToken) -> None: ...
    async def delete(self, key: str) -> None: ...
```

Serialized form (Redis value, file content): the JSON object the CLI store
already writes, `{"access_token", "refresh_token", "token_type", "expires_at",
"refresh_expires_at"}` with ISO-8601 timestamps. Deserialization validates the
same way the CLI's `_is_valid_token_data` does; anything invalid is a miss.

**`MemoryTokenCache`.** A module-level dictionary, `key -> CachedToken`, plus a
dictionary of per-key `asyncio.Lock`s. Expired entries are dropped on read.
`get_or_fetch(key, fetch)` runs `fetch` under the key's lock after re-checking
the entry, so concurrent clients in one process that miss at the same time wait
for one token request instead of each making their own. The dictionary is shared
by every `GundiClient` in the process; `clear_token_cache()` empties it, as
`auth.clear_discovery_cache()` does for discovery.

**`RedisTokenCache(url=None, client=None, *, socket_timeout=1.0)`.** Uses
`redis.asyncio`, imported lazily; installing it is the `redis` extra
(`pip install gundi-client-v2[redis]`). Constructing from a URL without the
package installed raises `TokenCacheConfigError` (a `GundiClientError`) at
construction time, not on first use. Keys are `gundi-client:token:<hash>`.
`set` uses `SET key value EX <ttl>` where `ttl` is the seconds until the later
of `expires_at` and `refresh_expires_at`, so Redis prunes entries itself and
never holds a token past its usefulness. Every operation runs with a short
socket timeout (default 1 second) so a hung Redis cannot stall an API call.

**`FileTokenCache(directory)`.** One file per key, `<directory>/<hash>.json`.
The directory is created with mode 0700; files are written 0600 to a temporary
name in the same directory and renamed into place, so a reader never sees a
partial file (the CLI's `config_store.write_private` pattern). Expired entries
are deleted when read. The URL form is `file:///absolute/dir`.

### Cache key

`sha256` over a canonical string of: the resolved token URL, the grant type
(`client_credentials` or `password`), client id, username (always), audience,
scope, and, for `client_credentials` only, the client secret. The hex digest
(first 32 characters) is the key. Reasons (amended 2026-09-08 after review):

- Including the client secret means a rotated secret never reuses a token minted
  under the old one, and two clients sharing an id with different secrets never
  collide. The password is excluded: a human password hashed next to guessable
  material would make every key name an offline password verifier, and a
  password change does not invalidate issued tokens.
- The username is always included: a CLI profile client carries a username and
  a restored token but no password, so several such clients under one client id
  would otherwise share an entry and adopt each other's tokens. (The CLI login
  itself uses the password grant, so its key never coincides with a profile
  client's; the point is isolating profile clients from each other.)
- The hash is one-way; the key discloses nothing about the credentials.
- The token URL must be the resolved one (after OIDC discovery), so a client
  configured by issuer and one configured by token URL share an entry.

Because the key is computed from the client's credentials, every `GundiClient`
with the same credentials in a process, and every process pointed at the same
Redis, shares one token. That is the intended sharing scope.

### Changes to `GundiClient`

Constructor: two new kwargs, following the existing kwarg-over-env pattern.

- `token_cache_url` (str): `redis://…`, `rediss://…`, `file:///dir`. Env:
  `GUNDI_TOKEN_CACHE_URL`. Unset means memory only.
- `token_cache` (TokenCache): an injected backend; takes precedence over the URL.

An unparseable URL or an unsupported scheme raises `TokenCacheConfigError` from
the constructor. The client holds `self._token_store`, a small coordinator
composed of the memory layer and the optional backend.

`get_access_token(force_refresh_token=False)` becomes:

1. If not forcing and the instance token is live, return it (unchanged).
2. Compute the key (requires the resolved token URL, so `_resolve_token_url`
   moves before the lookup).
3. Ask the memory layer, under the key's lock:
   - a live entry in memory: adopt it onto the instance and return;
   - otherwise ask the backend; a live entry there is stored in memory,
     adopted, and returned;
   - otherwise fetch: refresh grant if the best known entry (instance or cache)
     has a live refresh token, else full authentication (the existing
     `_refresh_token` logic, operating on a `CachedToken` instead of instance
     attributes); write the result to memory and the backend; adopt and return.
4. `force_refresh_token=True` (the auth-realm redirect in `_get`, `_post`,
   `_patch`, `_delete`, or an explicit caller) first re-reads the shared entry:
   if a sibling has already replaced the rejected token with a live one, that
   replacement is adopted; otherwise the key is deleted from memory and the
   backend and step 3's fetch branch runs. A token the server has rejected must
   not be served to any other client or replica (amended 2026-09-08: evicting
   unconditionally made N clients holding one rejected token mint N tokens and
   replay an exchanged refresh token). The re-read consults the backend when
   there is one, since memory may hold the rejected token itself; an instance
   with no token of its own never adopts (`gundi auth login` must reach the
   IdP). A backend outage during that re-read falls back to memory rather than
   discarding an in-process sibling's replacement. When the fetch fails: after a
   forced refresh the instance drops its token entirely; after a refresh grant
   the IdP answered with `invalid_grant` (400 on Keycloak, 403 on Auth0) or a
   bare 400 without an error code, the shared entry is deleted and the instance
   stops trying that refresh token; a 5xx, a rate limit, another 4xx, or a
   network failure leaves everything in place, and a network failure on the
   refresh grant is raised without attempting the full grant (amended 2026-09-08,
   second and third reviews: a dead-token marker had republished the rejected
   access token, a 5xx had discarded a valid refresh token, and a transport
   error escaped as a raw httpx exception). `auth._post_token` wraps transport
   errors into `AuthenticationError`, which carries `status_code`, `error` and
   `refresh_token_rejected`.

"Adopt" means setting `cached_token`, `cached_token_expires_at` and
`cached_token_refresh_expires_at` on the instance, so the CLI's
`token_store.apply_to_client` and any other code reading those attributes keeps
working. `_store_token` and `_expiry_with_buffer` stay; the 15-second buffer
also covers modest clock skew between the replica that wrote an entry and the one
reading it.

Across processes there is no distributed lock. Several replicas that miss at the
same moment each mint a token; the last write wins and the others are used once.
This is accepted: it happens on cold start or at expiry, a handful of tokens
instead of thousands.

### Failure handling

The cache never raises into an API call. A backend `get`, `set` or `delete` that
fails (connection refused, timeout, permission denied, disk full) is logged at
warning level with the backend type and error class, never the key or the token,
and treated as a miss (for `get`) or skipped (for `set`, `delete`). A corrupt or
malformed entry is a miss and is deleted. The memory layer cannot fail. The
warning is emitted once per backend per process per failure streak (a flag reset
on the next success), so a Redis outage does not flood logs on every call.

Configuration errors (bad URL, missing `redis` package) are the exception: they
raise at construction, because they are deployment mistakes that should fail
fast.

### Security

Access tokens are bearer credentials. In the runners, Redis already holds the
action-configuration cache, which contains integration credentials, so the token
cache lives in the same trust domain and adds no new class of secret to it.
Documentation states that the token cache database must be as protected as the
config cache. The file backend applies the CLI's permissions (0700 directory
when it creates one, 0600 files); it never re-modes a pre-existing directory
(amended 2026-09-08: `file:///tmp` as root would otherwise strip the sticky bit
from `/tmp`) and warns once if that directory is wider than 0700. The client
secret never leaves the process: it enters the key only as part of a one-way
hash; a password never enters it.

### Configuration reference

| Setting | Kwarg | Env | Meaning |
|---|---|---|---|
| Backend URL | `token_cache_url` | `GUNDI_TOKEN_CACHE_URL` | `redis://host:port/db`, `rediss://…`, `file:///dir`; unset = memory only |
| Injected backend | `token_cache` | — | any `TokenCache`; overrides the URL |

The `redis` extra: `pip install gundi-client-v2[redis]` adds `redis>=5,<9` (the surface used is get/set/delete with EX; the lockfile resolves redis 8.x).

### Template changes (separate PR in gundi-integration-action-runner)

1. Bump `gundi-client-v2` from `~=2.4.0` to `~=3.7.0`, with the fastapi and
   httpx bump this requires (documented in `MIGRATION.md`; cmore has already
   made it).
2. `app/settings/base.py`: `REDIS_TOKEN_CACHE_DB = env.int("REDIS_TOKEN_CACHE_DB", 2)`
   and `GUNDI_TOKEN_CACHE_URL = env.str("GUNDI_TOKEN_CACHE_URL",
   f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_TOKEN_CACHE_DB}")`.
3. One factory, `app/services/gundi.py: gundi_client()`, returning
   `GundiClient(token_cache_url=settings.GUNDI_TOKEN_CACHE_URL)`; every
   `GundiClient()` construction in the template (`gundi.py`, `config_manager.py`,
   `action_runner._portal`) goes through it.
4. `docs/configuration.md`: the two settings and what they do.
5. Downstream runners (EarthRanger, cmore) pick this up through the normal sync.

## Testing

Library, with respx for the token endpoint (as `tests/client/test_auth.py`),
fakeredis for the Redis backend (new dev dependency), `tmp_path` for files:

- Two `GundiClient` instances with the same credentials in one process: one
  token request.
- Ten concurrent first requests in one process: one token request (lock).
- Different secret, same client id: two keys, two requests.
- A fresh memory layer (cleared) with a populated Redis or file backend: zero
  token requests.
- Expired entry in the backend: one token request, entry replaced.
- Entry with a live refresh token but expired access token: the refresh grant is
  used, not full authentication.
- `force_refresh_token=True`: the entry is deleted from memory and the backend
  before the new request.
- Redis unreachable (connection error, timeout): the call succeeds, one warning,
  the token is cached in memory only. Same for a read-only file directory.
- Corrupt Redis value or file: treated as a miss and deleted.
- Redis TTL equals the later expiry; file permissions are 0600/0700; the file
  write is atomic (a failure mid-write leaves no partial file).
- Bad URL scheme, and `redis://` without the package: `TokenCacheConfigError`
  at construction.
- `clear_token_cache()` empties the process layer.
- Existing suites pass unchanged: the conftest gains an autouse fixture that
  clears the process layer, the same as the discovery cache.

Template: the factory passes the URL; the settings default composes from the
Redis settings. The template's conftest sets `settings.GUNDI_TOKEN_CACHE_URL`
to `None` for every test, so the existing send and reload tests run against a
memory-only client and never touch a Redis. One new test asserts the factory
passes the configured URL through.

## Out of scope

- Unifying the CLI token store with this cache.
- A distributed lock across replicas.
- Caching the per-integration Gundi API key that the runner's send path fetches
  on every batch (`get_integration_api_key`); that is a Gundi API call, not a
  Keycloak one, and a candidate for a separate template change.
- Any change to `GundiDataSenderClient` (API-key authenticated).

## Follow-ups noted

- CLI: replace `cli/token_store.py` with `FileTokenCache` keyed per environment.
- Template: cache the integration API key per integration id.
