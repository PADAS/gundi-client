# Design: gundi-client-v2 — routes CRUD + `get_routes_for_connection`

**Date:** 2026-05-30
**Author:** Chris Doehring (with Claude)
**Status:** Approved — pending spec review

## Context

`GundiClient` exposes only `get_route_details(route_id)` against `/v2/routes/`,
yet the cdip server's `RoutesView` is a full `viewsets.ModelViewSet` (list,
create, retrieve, update, partial-update, delete). The client SDK is therefore
missing list/create/update/delete for routes. Adding them is the next
logical step after the OIDC discovery + auth modernization in PR #41.

Separately, the user-facing concept "list the routes for a given Connection"
is achievable today via the server's `RouteFilter.provider` filter — no new
endpoint needed — but is not surfaced on the client. A small convenience
method makes that pattern discoverable.

## Goals

1. Expose all four missing CRUD verbs on `GundiClient` for `/v2/routes/`:
   `get_routes` (list), `create_route` (POST), `update_route` (PATCH),
   `delete_route`.
2. Add `get_routes_for_connection(connection_id)` — a one-line wrapper that
   issues `GET /v2/routes/?provider={connection_id}`.
3. Add the two missing HTTP-verb helpers (`_patch`, `_delete`) on
   `GundiClient` mirroring the existing `_post` shape (auth header, 302
   login-redirect retry, error mapping via `errors.raise_for_status`).
4. Test coverage for each new method against respx-mocked responses,
   matching the existing patterns in `tests/client/`.

## Non-goals

- Write methods for connections, integrations, or other resources. Server
  has them, client doesn't, but they are out of scope here.
- Bulk operations on routes — server is single-create-only at `/v2/routes/`.
- Resource-grouping refactor (`client.routes.list()` etc.). Larger churn;
  not "small follow-up."
- TypedDict / pydantic input models for the `data` dict on create/update.
  The `dict` API is a deliberate choice for forward-compat with server
  schema additions; typed shapes can come later if useful.
- A PUT (full-replace) `update_route`. PATCH covers the common case and is
  what DRF callers typically want.

## Public API additions

```python
class GundiClient:
    async def get_routes(self, params: dict = None) -> List[Route]
    async def get_routes_for_connection(self, connection_id) -> List[Route]
    async def get_route_details(self, route_id) -> Route             # already exists
    async def create_route(self, data: dict) -> Route
    async def update_route(self, route_id, data: dict) -> Route      # PATCH (partial)
    async def delete_route(self, route_id) -> None
```

### Method semantics

**`get_routes(params=None)`** — `GET /v2/routes/`. Returns a list of `Route`
objects, parsed via the existing `_parse_list_response` helper (handles
both bare-list and `{results, next}` envelope responses). `params` is
forwarded to the GET. Common server-side filters available on
`RouteFilter`: `provider`, `provider__in`, `destination`, `destination__in`,
`destination_url`, `destination_url__in`, `id`, `id__in`. Default
pagination per cdip settings is `PAGE_SIZE=20` cursor pagination — first
page only is returned (matching how `get_connections` works today).

**`get_routes_for_connection(connection_id)`** — convenience wrapper:

```python
async def get_routes_for_connection(self, connection_id) -> List[Route]:
    """List routes where the given connection appears as a data provider."""
    return await self.get_routes(params={"provider": str(connection_id)})
```

The filter param is `provider` (not `data_providers`) — matches the alias
declared in `cdip_admin/integrations/filters.py:RouteFilter`.

**`create_route(data)`** — `POST /v2/routes/`. Body is the `data` dict
as-is. Returns the created `Route`. Server-side write fields (per
`RouteCreateUpdateSerializer`):

| Field | Required | Shape |
|---|---|---|
| `name` | yes | string |
| `owner` | yes | UUID (Organization) |
| `data_providers` | yes | list of Integration UUIDs |
| `destinations` | yes | list of Integration UUIDs |
| `configuration` | no | UUID of existing `RouteConfiguration` OR nested config object |
| `additional` | no | free-form dict |

**`update_route(route_id, data)`** — `PATCH /v2/routes/{id}/`. Body is the
`data` dict as-is; only fields included in `data` are updated.

**`delete_route(route_id)`** — `DELETE /v2/routes/{id}/`. Returns `None`
on `204 No Content` success; raises `errors.GundiAPIError` on 4xx/5xx.

## Private HTTP plumbing additions

Currently `GundiClient` has `_get` and `_post`. Add `_patch` and `_delete`
modeled exactly on `_post`'s shape, including the 302 login-redirect retry:

```python
async def _patch(self, url, data: dict = None, params=None, headers=None, **kwargs):
    headers = headers or {}
    auth_headers = await self.get_auth_header()
    response = await self._session.patch(
        url, json=data, params=params,
        headers={**auth_headers, **headers}, **kwargs,
    )
    if response.status_code == 302 and "auth/realms" in response.headers.get("location", ""):
        auth_headers = await self.get_auth_header(force_refresh_token=True)
        response = await self._session.patch(
            url, json=data, params=params,
            headers={**auth_headers, **headers}, **kwargs,
        )
    return response


async def _delete(self, url, params=None, headers=None, **kwargs):
    headers = headers or {}
    auth_headers = await self.get_auth_header()
    response = await self._session.delete(
        url, params=params,
        headers={**auth_headers, **headers}, **kwargs,
    )
    if response.status_code == 302 and "auth/realms" in response.headers.get("location", ""):
        auth_headers = await self.get_auth_header(force_refresh_token=True)
        response = await self._session.delete(
            url, params=params,
            headers={**auth_headers, **headers}, **kwargs,
        )
    return response
```

Each new public route method routes its response through
`self._raise_for_status(response)` — so 4xx/5xx surface as `GundiAPIError`
with the body in `.detail`, matching existing methods.

## Public method bodies

```python
async def get_routes(self, params: dict = None) -> List[Route]:
    url = f"{self.routes_endpoint}/"
    response = await self._get(url, params=params)
    self._raise_for_status(response)
    return self._parse_list_response(response.json(), Route)


async def get_routes_for_connection(self, connection_id) -> List[Route]:
    return await self.get_routes(params={"provider": str(connection_id)})


async def create_route(self, data: dict) -> Route:
    url = f"{self.routes_endpoint}/"
    response = await self._post(url, data=data)
    self._raise_for_status(response)
    return Route.parse_obj(response.json())


async def update_route(self, route_id, data: dict) -> Route:
    url = f"{self.routes_endpoint}/{route_id}/"
    response = await self._patch(url, data=data)
    self._raise_for_status(response)
    return Route.parse_obj(response.json())


async def delete_route(self, route_id) -> None:
    url = f"{self.routes_endpoint}/{route_id}/"
    response = await self._delete(url)
    self._raise_for_status(response)
    # 204 No Content is expected on success; no body to return.
```

## Test plan

New file: `tests/client/test_routes.py`. All tests use respx-mocked
responses against `gundi_client_v2`'s `routes_endpoint` and follow the
patterns established in `test_read_methods.py` and `test_password_grant.py`.

- **`test_get_routes_parses_results_envelope`** — `{"results": [route_dict], "next": null}` response → returns a one-element list of `Route`.
- **`test_get_routes_parses_bare_list`** — `[route_dict]` response → returns same.
- **`test_get_routes_for_connection_filters_by_provider`** — verifies the request URL carries `?provider=<connection_id>`.
- **`test_create_route_posts_with_data`** — POST body equals the `data` dict; response parses as `Route`.
- **`test_create_route_raises_gundi_api_error_on_400`** — 400 with `{"detail": "..."}` body → `GundiAPIError(400, "...")`.
- **`test_update_route_patches_with_partial_data`** — PATCH verb (assert via `route.calls.last.request.method == "PATCH"`); body == `data`.
- **`test_delete_route_issues_delete_and_returns_none`** — DELETE verb, 204 response → method returns `None`.
- **`test_delete_route_raises_on_404`** — 404 → `GundiAPIError(404, ...)`.

A small route-dict fixture lives in `tests/conftest.py` already
(`route_details`) — reuse it where applicable. For `get_routes`, wrap it
in a list (or `{"results": [...]}`).

## File inventory

| Change | Path |
|---|---|
| Modify | `gundi_client_v2/client.py` (add `_patch`, `_delete`, 5 new public methods) |
| Modify | `gundi_client_v2/__init__.py` (version bump) |
| Modify | `README.md` (add the new methods to the Usage: GundiClient section + filter docs) |
| Create | `tests/client/test_routes.py` (the 8 tests above) |

## Branch placement

Stack on **`cd/v2-oidc-discovery`** (PR #41 branch). Rationale:
- Continues the auth + usability arc from #41.
- When #41 merges to `v2`, this PR's base auto-retargets — no manual rebase
  unless conflicts arise (none expected: routes work doesn't touch auth code).
- Alternative — fresh branch off `v2` — works equally well but reasonably
  requires concurrent maintenance of both PRs against `v2`.

## Versioning

Adds public methods → minor bump.
- If PR #41 has shipped: `2.6.0 → 2.7.0`.
- If PR #41 has not yet shipped: roll the routes work into the same 2.6.0
  release, no separate bump on this PR.

## Migration impact

None. Pure additions to the SDK surface. Existing callers see no changes.

## Out-of-scope follow-ups (worth noting, not in this PR)

- **Schema typing for the write `data` dict** — `TypedDict` or a small
  pydantic input model for create/update payloads, for better
  discoverability and editor autocomplete. Cheap, defensible follow-up.
- **Write methods for connections, integrations, sources** — symmetric
  scope expansion. Same plumbing (`_patch`/`_delete`) is reusable.
- **Bulk-create support for resources where the server eventually adds it.**
- **Resource-grouping refactor** (`client.routes.list/get/create/update/delete`,
  `client.connections.list/get`, etc.) — uniformizes the SDK shape. Larger
  refactor; only worth it if the client surface keeps growing.
