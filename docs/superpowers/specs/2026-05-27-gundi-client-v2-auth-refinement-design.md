# Design: gundi-client-v2 PR split + OAuth2 auth refinement

**Date:** 2026-05-27
**Author:** Chris Doehring (with Claude)
**Status:** Approved — pending spec review

## Context

The branch `cd/add-password-grant-support` carries 4 commits on top of `origin/v2`
(the home branch of the `gundi-client-v2` package, currently v2.4.1). The `main`
branch belongs to the *separate* v1 `gundi-client` package (`PortalApi`, poetry) and
is **not** an ancestor of v2 work — a `git merge main` was attempted and aborted
because it reintroduced the entire v1 package. **All work here bases on `origin/v2`;
sync with `git merge origin/v2`, never `main`.**

The 4 commits are tangled (the first is a kitchen-sink commit mixing README, tooling,
auth, errors, and settings), so the PRs below are **rebuilt by concern** from the
`origin/v2..HEAD` diff rather than cherry-picked. `gundi_client_v2/errors.py` exists as
an empty file at `origin/v2`; PR3 fills it in.

## Goals

1. Split the bundled work into 5 reviewable, concern-scoped PRs.
2. Refine authentication to comply with OAuth2 standards as much as possible.
3. Add test coverage for every behavior introduced (currently none of the new code is tested).

## Non-goals

- Touching the v1 `gundi-client` package or `main`.
- Unrelated refactoring beyond what serves these concerns.

## PR breakdown (stacked, in order)

PRs 2–5 all touch `client.py`, so they **stack**: each branches off the previous and
rebases forward as earlier PRs merge.

| PR | Title | Key files |
|----|-------|-----------|
| PR1 | `chore: migrate poetry → uv` | `pyproject.toml`, `uv.lock`, delete `poetry.lock`, `.gitignore` (+`.DS_Store`) |
| PR2 | `refactor: oauth_* kwargs + settings (keycloak_* compat)` | `settings.py`, `client.py`, tests |
| PR3 | `feat: errors module + _raise_for_status` | `errors.py`, `client.py`, tests |
| PR4 | `feat: get_connections / get_integrations` | `client.py`, `examples/`, `README.md`, tests |
| PR5 | `feat: password grant + OAuth2-compliant token/refresh` | `auth.py`, `client.py`, `settings.py`, `README.md`, tests |

The large README rewrite splits between PR4 (read methods) and PR5 (auth usage).

## Auth refinement design (PR5)

### `auth.py` — standalone functions + shared helper

- `_token_request(session, oauth_token_url, payload) -> OAuthToken`
  POSTs `payload` to the token endpoint. On `HTTPStatusError`, parses the RFC 6749 §5.2
  error body `{error, error_description}` and raises `AuthenticationError` with that
  detail; falls back to the HTTP status code when the body is not parseable JSON.
  Returns `OAuthToken.parse_obj(response.json())` on success.

- `get_access_token(session, oauth_token_url, client_id, client_secret, audience=None, scope="openid")`
  Existing Keycloak UMA-ticket grant (`grant_type=urn:ietf:params:oauth:grant-type:uma-ticket`).
  Refined: include `audience` in the payload **only when set**; `scope` configurable.

- `get_access_token_password_grant(session, oauth_token_url, client_id, username, password, audience=None, scope="openid")`
  ROPC grant (`grant_type=password`). **No `client_secret`** — used only with a public
  client. `audience` included only when set; `scope` configurable.
  (Note: ROPC is discouraged by OAuth 2.1 / RFC 9700, retained because the deployment requires it.)

- `refresh_access_token(session, oauth_token_url, client_id, refresh_token, client_secret=None, scope="openid")`
  **New.** `grant_type=refresh_token` per RFC 6749 §6. Sends `client_secret` only when
  provided (confidential case); omits it for the public/password case.

### `client._refresh_token()` orchestration

1. If `cached_token` has a `refresh_token` **and** `cached_token_refresh_expires_at` is in
   the future → attempt `refresh_access_token`. On `invalid_grant`/any
   `AuthenticationError`, fall through to full re-auth (do not hard-fail).
2. Full re-authentication by **credential precedence**:
   - `username` + `password` present → `get_access_token_password_grant`
   - elif `client_id` + `client_secret` present → `get_access_token` (uma-ticket)
   - else → raise `AuthenticationError("No credentials configured. Provide username/password or client_id/client_secret.")`
3. Store the token and track **both** expiries (with a 15s skew buffer):
   - `cached_token_expires_at = now + (expires_in - 15)`
   - `cached_token_refresh_expires_at = now + (refresh_expires_in - 15)` when present

### Decisions (approved)

- **Credential precedence:** when both user creds and client creds are configured,
  password grant wins (matches current behavior).
- **Refresh preferred:** whenever a live refresh token exists, the refresh grant is used
  in preference to full re-auth, regardless of which grant minted it. Net effect: a user's
  password is transmitted once, then only the refresh token circulates.
- **Graceful fallback:** a failed refresh falls back to full re-auth rather than erroring.

### `settings.py`

- Add `OAUTH_SCOPE = env.str("OAUTH_SCOPE", "openid")`.
- `GUNDI_USERNAME` / `GUNDI_PASSWORD` already present.
- `OAUTH_*` names preferred with `KEYCLOAK_*` fallbacks (already in place from PR2).

## Test plan

All token-endpoint interactions are respx-mocked, following the existing
`tests/client/` pattern (token POST mocked per test).

- **PR2:** client built with `oauth_*` kwargs authenticates successfully; `keycloak_*`
  kwargs still resolve via backward-compat fallback.
- **PR3:** API 4xx/5xx → `GundiAPIError(status_code, detail)` with body detail; token
  endpoint failure → `AuthenticationError`.
- **PR4:** `get_connections` parses both a bare JSON list and a DRF `{results: [...]}`
  envelope; `get_integrations` generator yields across paginated `next` links and handles
  a single page.
- **PR5:**
  - password-grant payload asserts `grant_type=password`, **no** `client_secret`,
    `scope` present, `audience` present only when configured;
  - refresh flow: after an initial password-grant token, a forced refresh issues
    `grant_type=refresh_token` and the password is **not** resent;
  - refresh failure (`invalid_grant`) falls back to full re-auth;
  - error-body parsing surfaces `error_description` in `AuthenticationError`;
  - `scope` override is honored;
  - credential precedence (password grant wins when both sets present);
  - no-credentials configuration raises `AuthenticationError`.

## Housekeeping

Removed / git-ignored (not committed into any PR): `.DS_Store`, `.cache_ggshield`,
`.vscode/`, `licenses.txt`, `requirements.txt`, `testing.py`, `testit.py`. Treated as
scratch/local artifacts.

## Sequencing notes

- Cut clean topic branches from `origin/v2`; do not carry the tangled commits forward.
- Land PR1→PR5 in order; rebase each open PR after the prior one merges.
- The original `cd/add-password-grant-support` branch is retained read-only as the
  source diff until all PRs land.
