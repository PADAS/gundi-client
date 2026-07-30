# GUNDI_OAUTH_* Env Var Prefix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `GUNDI_OAUTH_*` the preferred env var names for OAuth config, with silent fallback to the existing `OAUTH_*` (and, in the library, `KEYCLOAK_*`) names.

**Architecture:** Two lookup layers change: `gundi_client_v2/settings.py` (environs-based, used by the library) grows one link at the front of each chain; the CLI (`gundi_client_v2/cli/_client.py`, reads `os.environ` directly) gets a tiny `_getenv()` helper that prefers the `GUNDI_`-prefixed spelling. Docs/examples/error messages switch to the new names. Spec: `docs/superpowers/specs/2026-07-30-gundi-oauth-env-prefix-design.md`.

**Tech Stack:** Python, environs, typer CLI, pytest (+ monkeypatch, respx, CliRunner). Run tests with `uv run pytest`.

## Global Constraints

- New preferred names: `GUNDI_OAUTH_ISSUER`, `GUNDI_OAUTH_TOKEN_URL`, `GUNDI_OAUTH_CLIENT_ID`, `GUNDI_OAUTH_CLIENT_SECRET`, `GUNDI_OAUTH_AUDIENCE`, `GUNDI_OAUTH_SCOPE`.
- Library fallback chain: `GUNDI_OAUTH_X` → `OAUTH_X` → `KEYCLOAK_X` (no `KEYCLOAK_*` link for `TOKEN_URL`/`SCOPE`; `SCOPE` defaults to `"openid"`).
- CLI fallback chain: `GUNDI_OAUTH_X` → `OAUTH_X` only (the CLI never accepted `KEYCLOAK_*`).
- Silent fallback — NO deprecation warnings anywhere.
- Python constants in `settings.py` keep their `OAUTH_*` names (and the existing `KEYCLOAK_*` aliases). Do not rename module attributes.
- `LOG_LEVEL` and `SENSORS_API_BASE_URL` are OUT OF SCOPE — do not touch them.
- Existing old-name tests must stay untouched and passing (they are the back-compat regression suite).
- Version ships as `3.7.0` (`gundi_client_v2/__init__.py`).
- Code style: `black` (CI runs `black --check`). Run `uv run black .` before each commit.
- The `site/` directory is generated mkdocs output — never edit it. Historical files under `docs/superpowers/` are records — never edit them.

---

### Task 1: settings.py lookup chains

**Files:**
- Modify: `gundi_client_v2/settings.py:18-28`
- Test: `tests/client/test_settings.py`

**Interfaces:**
- Consumes: existing `env = Env()` setup and the `_isolate_envfile` / `_restore_settings_after_test` test helpers already in `tests/client/test_settings.py`.
- Produces: module constants `settings.OAUTH_ISSUER`, `settings.OAUTH_TOKEN_URL`, `settings.OAUTH_CLIENT_ID`, `settings.OAUTH_CLIENT_SECRET`, `settings.OAUTH_AUDIENCE`, `settings.OAUTH_SCOPE` — same names and types as today (str or None; `OAUTH_SCOPE` always str), now also populated from `GUNDI_OAUTH_*`. Task 2 and the library rely on these exact names.

- [ ] **Step 1: Write the failing tests**

Append to `tests/client/test_settings.py` (it already imports `importlib`, `pytest`, and `settings_module`, and defines `_isolate_envfile`):

```python
_GUNDI_OAUTH_VARS = (
    "GUNDI_OAUTH_ISSUER",
    "GUNDI_OAUTH_TOKEN_URL",
    "GUNDI_OAUTH_CLIENT_ID",
    "GUNDI_OAUTH_CLIENT_SECRET",
    "GUNDI_OAUTH_AUDIENCE",
    "GUNDI_OAUTH_SCOPE",
)


def _clear_oauth_env(monkeypatch):
    """Drop every spelling of the OAuth vars so precedence tests start clean."""
    for name in _GUNDI_OAUTH_VARS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.removeprefix("GUNDI_"), raising=False)
        monkeypatch.delenv(name.replace("GUNDI_OAUTH_", "KEYCLOAK_"), raising=False)


def test_gundi_oauth_names_work_alone(monkeypatch, tmp_path):
    _isolate_envfile(monkeypatch, tmp_path)
    _clear_oauth_env(monkeypatch)
    monkeypatch.setenv("GUNDI_OAUTH_ISSUER", "https://idp.example.com/realms/x")
    monkeypatch.setenv("GUNDI_OAUTH_TOKEN_URL", "https://idp.example.com/token")
    monkeypatch.setenv("GUNDI_OAUTH_CLIENT_ID", "my-client")
    monkeypatch.setenv("GUNDI_OAUTH_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("GUNDI_OAUTH_AUDIENCE", "gundi-api")
    monkeypatch.setenv("GUNDI_OAUTH_SCOPE", "openid profile")
    reloaded = importlib.reload(settings_module)
    assert reloaded.OAUTH_ISSUER == "https://idp.example.com/realms/x"
    assert reloaded.OAUTH_TOKEN_URL == "https://idp.example.com/token"
    assert reloaded.OAUTH_CLIENT_ID == "my-client"
    assert reloaded.OAUTH_CLIENT_SECRET == "shhh"
    assert reloaded.OAUTH_AUDIENCE == "gundi-api"
    assert reloaded.OAUTH_SCOPE == "openid profile"


def test_gundi_oauth_prefix_wins_over_oauth_and_keycloak(monkeypatch, tmp_path):
    _isolate_envfile(monkeypatch, tmp_path)
    _clear_oauth_env(monkeypatch)
    monkeypatch.setenv("GUNDI_OAUTH_CLIENT_ID", "prefixed")
    monkeypatch.setenv("OAUTH_CLIENT_ID", "generic")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "legacy")
    reloaded = importlib.reload(settings_module)
    assert reloaded.OAUTH_CLIENT_ID == "prefixed"


def test_oauth_still_wins_over_keycloak(monkeypatch, tmp_path):
    _isolate_envfile(monkeypatch, tmp_path)
    _clear_oauth_env(monkeypatch)
    monkeypatch.setenv("OAUTH_CLIENT_ID", "generic")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "legacy")
    reloaded = importlib.reload(settings_module)
    assert reloaded.OAUTH_CLIENT_ID == "generic"


def test_keycloak_fallback_still_works(monkeypatch, tmp_path):
    _isolate_envfile(monkeypatch, tmp_path)
    _clear_oauth_env(monkeypatch)
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "legacy")
    reloaded = importlib.reload(settings_module)
    assert reloaded.OAUTH_CLIENT_ID == "legacy"
    assert reloaded.KEYCLOAK_CLIENT_ID == "legacy"  # alias constant still mirrors


def test_gundi_oauth_scope_default(monkeypatch, tmp_path):
    _isolate_envfile(monkeypatch, tmp_path)
    _clear_oauth_env(monkeypatch)
    reloaded = importlib.reload(settings_module)
    assert reloaded.OAUTH_SCOPE == "openid"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/client/test_settings.py -v`
Expected: `test_gundi_oauth_names_work_alone` and `test_gundi_oauth_prefix_wins_over_oauth_and_keycloak` FAIL (the `GUNDI_OAUTH_*` values are ignored, constants come back None/generic). The other three may already pass — that's fine, they pin existing behavior.

- [ ] **Step 3: Implement the lookup chains**

In `gundi_client_v2/settings.py`, replace lines 18–28 (the comment block and the six assignments) with:

```python
# OAuth settings — GUNDI_OAUTH_* preferred; OAUTH_* and KEYCLOAK_* accepted for
# backward compatibility. The token URL is either set directly via
# GUNDI_OAUTH_TOKEN_URL or discovered at runtime from GUNDI_OAUTH_ISSUER via the
# OIDC discovery document.
OAUTH_ISSUER = env.str(
    "GUNDI_OAUTH_ISSUER", env.str("OAUTH_ISSUER", env.str("KEYCLOAK_ISSUER", None))
)
OAUTH_TOKEN_URL = env.str("GUNDI_OAUTH_TOKEN_URL", env.str("OAUTH_TOKEN_URL", None))
OAUTH_CLIENT_ID = env.str(
    "GUNDI_OAUTH_CLIENT_ID",
    env.str("OAUTH_CLIENT_ID", env.str("KEYCLOAK_CLIENT_ID", None)),
)
OAUTH_CLIENT_SECRET = env.str(
    "GUNDI_OAUTH_CLIENT_SECRET",
    env.str("OAUTH_CLIENT_SECRET", env.str("KEYCLOAK_CLIENT_SECRET", None)),
)
OAUTH_AUDIENCE = env.str(
    "GUNDI_OAUTH_AUDIENCE",
    env.str("OAUTH_AUDIENCE", env.str("KEYCLOAK_AUDIENCE", None)),
)
OAUTH_SCOPE = env.str("GUNDI_OAUTH_SCOPE", env.str("OAUTH_SCOPE", "openid"))
```

Leave everything else in the file untouched (including the `KEYCLOAK_* = OAUTH_*` alias block below it).

- [ ] **Step 4: Run the test file to verify all pass**

Run: `uv run pytest tests/client/test_settings.py -v`
Expected: ALL PASS (new tests plus the five pre-existing ones).

- [ ] **Step 5: Format and commit**

```bash
uv run black gundi_client_v2/settings.py tests/client/test_settings.py
git add gundi_client_v2/settings.py tests/client/test_settings.py
git commit -m "feat: prefer GUNDI_OAUTH_* env vars in settings, keep OAUTH_*/KEYCLOAK_* fallback"
```

---

### Task 2: CLI env resolution and error messages

**Files:**
- Modify: `gundi_client_v2/cli/_client.py` (docstrings at 2-7 and 32-46; `_REQUIRED_ENV` at 24-28; `build_client()` at 47-83; `_build_profile_client()` at 183; `build_client_for_login()` at 208-210)
- Test: `tests/test_cli.py`, `tests/test_cli_auth.py`

**Interfaces:**
- Consumes: nothing from Task 1 — the CLI reads `os.environ` directly, not `settings`.
- Produces: module-private helper `_getenv(name: str) -> Optional[str]` in `gundi_client_v2/cli/_client.py` that returns `os.environ.get(f"GUNDI_{name}") or os.environ.get(name)`. `build_client()`, `_build_profile_client()`, and `build_client_for_login()` keep their existing signatures. Missing-config error text now names `GUNDI_OAUTH_CLIENT_ID`, `GUNDI_OAUTH_CLIENT_SECRET (or GUNDI_USERNAME + GUNDI_PASSWORD)`, and `GUNDI_OAUTH_ISSUER (or GUNDI_OAUTH_TOKEN_URL)`.

- [ ] **Step 1: Update test hygiene helpers so new-name env vars can't leak in**

The new prefix takes precedence, so a developer's real `.env` exporting `GUNDI_OAUTH_*` would silently override fixture values. In `tests/test_cli.py`, extend `_clear_auth_env` (lines 35-49) to:

```python
def _clear_auth_env(monkeypatch):
    """Drop every auth env var so each fixture starts from a known-empty state.

    Without this, a developer's real .env (loaded by the client at import) could
    leak username/password/issuer into a test and change the selected grant.
    """
    for var in (
        "OAUTH_CLIENT_ID",
        "OAUTH_CLIENT_SECRET",
        "OAUTH_TOKEN_URL",
        "OAUTH_ISSUER",
        "OAUTH_AUDIENCE",
        "GUNDI_USERNAME",
        "GUNDI_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv(f"GUNDI_{var}", raising=False)
```

In `tests/test_cli.py::test_missing_env_var_exits_2` (line 335), replace the inline delenv loop with `_clear_auth_env(monkeypatch)` plus `monkeypatch.delenv("GUNDI_API_BASE_URL", raising=False)`. In `test_missing_token_endpoint_exits_2` (line 354), add `_clear_auth_env(monkeypatch)` as the first line (before the setenv calls).

In `tests/test_cli_auth.py`, extend the clear loop at line 18 from `("OAUTH_CLIENT_SECRET", "GUNDI_PASSWORD", "GUNDI_USERNAME")` to `("OAUTH_CLIENT_SECRET", "GUNDI_OAUTH_CLIENT_SECRET", "GUNDI_PASSWORD", "GUNDI_USERNAME")`.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_cli.py` (uses the existing `runner`, `BASE_URL`, `TOKEN_URL`, `INTEGRATIONS_URL`, `_mock_auth`, and `_clear_auth_env` helpers):

```python
@pytest.fixture
def cli_env_gundi_prefixed(monkeypatch):
    """Client-credentials configured entirely via the new GUNDI_OAUTH_* names."""
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GUNDI_API_BASE_URL", BASE_URL)
    monkeypatch.setenv("GUNDI_OAUTH_CLIENT_ID", "confidential-client")
    monkeypatch.setenv("GUNDI_OAUTH_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("GUNDI_OAUTH_TOKEN_URL", TOKEN_URL)


def test_list_with_gundi_prefixed_env(
    cli_env_gundi_prefixed, auth_token_response, destination_integration_details
):
    with respx.mock(assert_all_called=False) as mock:
        _mock_auth(mock, auth_token_response)
        mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 0, result.output
    assert destination_integration_details["id"] in result.output


def test_gundi_prefixed_wins_over_bare_name(
    cli_env, auth_token_response, destination_integration_details, monkeypatch
):
    # cli_env sets the bare OAUTH_* names; the GUNDI_ spelling must win.
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "wrong-secret")
    monkeypatch.setenv("GUNDI_OAUTH_CLIENT_SECRET", "shhh")
    with respx.mock(assert_all_called=False) as mock:
        token_route = mock.post(TOKEN_URL).respond(
            status_code=httpx.codes.OK, json=auth_token_response
        )
        mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )

        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 0, result.output
    assert b"client_secret=shhh" in token_route.calls.last.request.content


def test_missing_env_error_names_gundi_prefixed_vars(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.delenv("GUNDI_API_BASE_URL", raising=False)

    result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 2, result.output
    assert "GUNDI_OAUTH_CLIENT_ID" in result.output
    assert "GUNDI_OAUTH_ISSUER (or GUNDI_OAUTH_TOKEN_URL)" in result.output
    assert (
        "GUNDI_OAUTH_CLIENT_SECRET (or GUNDI_USERNAME + GUNDI_PASSWORD)"
        in result.output
    )
```

Note: existing message assertions like `assert "OAUTH_ISSUER" in result.output` (lines 351, 365) keep passing unchanged, because `GUNDI_OAUTH_ISSUER` contains the substring `OAUTH_ISSUER`. Do not edit them.

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v -k "gundi_prefixed or names_gundi"`
Expected: all three FAIL — `test_list_with_gundi_prefixed_env` exits 2 (vars not recognized), `test_gundi_prefixed_wins_over_bare_name` authenticates with `wrong-secret`, `test_missing_env_error_names_gundi_prefixed_vars` finds the old un-prefixed names in the message.

- [ ] **Step 4: Implement the CLI changes**

In `gundi_client_v2/cli/_client.py`:

a) Delete the `_REQUIRED_ENV` dict (lines 24-28) and add the helper in its place:

```python
def _getenv(name: str) -> Optional[str]:
    """Resolve an OAuth env var, preferring the GUNDI_-prefixed spelling
    (``GUNDI_OAUTH_X``) over the bare ``OAUTH_X`` kept for backward compatibility."""
    return os.environ.get(f"GUNDI_{name}") or os.environ.get(name)
```

b) Replace the body of `build_client()` with (docstring updated to the new names):

```python
def build_client() -> GundiClient:
    """Construct a GundiClient from environment variables.

    Mirrors the library's auth rules. A ``client_id`` is always required, plus:

    - **Credentials** — either ``GUNDI_USERNAME`` + ``GUNDI_PASSWORD`` (password
      grant, public client) or ``GUNDI_OAUTH_CLIENT_SECRET`` (client-credentials,
      confidential client). When both are present the client uses the password
      grant.
    - **Token endpoint** — ``GUNDI_OAUTH_ISSUER`` (preferred; resolved via OIDC
      discovery, IdP-agnostic) or an explicit ``GUNDI_OAUTH_TOKEN_URL``. When
      both are set, the explicit URL wins.

    ``GUNDI_OAUTH_AUDIENCE`` is forwarded when set (some IdPs require it). Each
    ``GUNDI_OAUTH_*`` var also accepts its bare ``OAUTH_*`` spelling for backward
    compatibility. Exits with code 2, listing what's missing, when required
    configuration is absent.
    """
    kwargs = {}
    missing = []
    if base_url := os.environ.get("GUNDI_API_BASE_URL"):
        kwargs["base_url"] = base_url
    else:
        missing.append("GUNDI_API_BASE_URL")
    if client_id := _getenv("OAUTH_CLIENT_ID"):
        kwargs["oauth_client_id"] = client_id
    else:
        missing.append("GUNDI_OAUTH_CLIENT_ID")

    # Credentials: password grant (username + password) or client-credentials
    # (client_secret). At least one full set is required.
    username = os.environ.get("GUNDI_USERNAME")
    password = os.environ.get("GUNDI_PASSWORD")
    client_secret = _getenv("OAUTH_CLIENT_SECRET")
    if username:
        kwargs["username"] = username
    if password:
        kwargs["password"] = password
    if client_secret:
        kwargs["oauth_client_secret"] = client_secret
    if not (username and password) and not client_secret:
        missing.append("GUNDI_OAUTH_CLIENT_SECRET (or GUNDI_USERNAME + GUNDI_PASSWORD)")

    # Token endpoint: discovery via GUNDI_OAUTH_ISSUER preferred,
    # GUNDI_OAUTH_TOKEN_URL is the explicit fallback. The client prefers
    # oauth_token_url when both exist.
    if issuer := _getenv("OAUTH_ISSUER"):
        kwargs["oauth_issuer"] = issuer
    if token_url := _getenv("OAUTH_TOKEN_URL"):
        kwargs["oauth_token_url"] = token_url
    if not issuer and not token_url:
        missing.append("GUNDI_OAUTH_ISSUER (or GUNDI_OAUTH_TOKEN_URL)")

    if missing:
        typer.echo(f"Error: missing required env vars: {', '.join(missing)}", err=True)
        raise typer.Exit(2)
    if audience := _getenv("OAUTH_AUDIENCE"):
        kwargs["oauth_audience"] = audience
    return GundiClient(**kwargs)
```

c) In `_build_profile_client()` (line 183), change `os.environ.get("OAUTH_CLIENT_SECRET")` to `_getenv("OAUTH_CLIENT_SECRET")`.

d) In `build_client_for_login()` (lines 208-210), change `os.environ.get("OAUTH_CLIENT_SECRET")` to `_getenv("OAUTH_CLIENT_SECRET")`.

e) In the module docstring (lines 1-7), no env var names appear — leave it.

- [ ] **Step 5: Run the CLI test files to verify all pass**

Run: `uv run pytest tests/test_cli.py tests/test_cli_auth.py -v`
Expected: ALL PASS — new tests plus every pre-existing old-name test.

- [ ] **Step 6: Format and commit**

```bash
uv run black gundi_client_v2/cli/_client.py tests/test_cli.py tests/test_cli_auth.py
git add gundi_client_v2/cli/_client.py tests/test_cli.py tests/test_cli_auth.py
git commit -m "feat(cli): prefer GUNDI_OAUTH_* env vars, name them in error messages"
```

---

### Task 3: Docs, examples, and docstrings sweep

**Files:**
- Modify: `README.md`, `MIGRATION.md`, `docs/troubleshooting.md`, `docs/getting-started/auth-setup.md`, `docs/getting-started/first-request.md`, `docs/authentication/overview.md`, `docs/authentication/password-grant.md`, `docs/authentication/client-credentials.md`, `docs/authentication/oidc-discovery.md`, `docs/authentication/refresh-and-errors.md`, `examples/README.md`, `examples/list_connections_password_grant.py`, `examples/list_connections_discovery.py`, `examples/list_connections_client_credentials.py`, `examples/send_observations.py`, `.claude/skills/using-the-gundi-cli/SKILL.md`, `gundi_client_v2/client.py:279-300` (docstring only)

**Interfaces:**
- Consumes: the behavior shipped by Tasks 1–2 (new names actually work).
- Produces: nothing programmatic — documentation only. No code behavior may change in this task; `gundi_client_v2/client.py` edits are docstring text only.

- [ ] **Step 1: Enumerate every real occurrence**

Run: `grep -rn "OAUTH_\|KEYCLOAK_" README.md MIGRATION.md docs examples .claude gundi_client_v2/client.py --include="*.md" --include="*.py" | grep -v "docs/superpowers" | grep -v "GUNDI_OAUTH"`

This is the authoritative worklist (the spec's file list above is the expected result). Skip `site/` (generated) and `docs/superpowers/` (historical records).

- [ ] **Step 2: Update the library docstring**

In `gundi_client_v2/client.py` lines 279-300, rewrite the env-var references in the `GundiClient` docstring so each parameter names the new form first, e.g.:

- `Env: ``GUNDI_OAUTH_CLIENT_ID`` / ``OAUTH_CLIENT_ID`` / ``KEYCLOAK_CLIENT_ID``.`
- `Env: ``GUNDI_OAUTH_CLIENT_SECRET`` / ``OAUTH_CLIENT_SECRET`` / ``KEYCLOAK_CLIENT_SECRET``.`
- `Env: ``GUNDI_OAUTH_TOKEN_URL`` / ``OAUTH_TOKEN_URL``.`
- `Env: ``GUNDI_OAUTH_ISSUER`` / ``OAUTH_ISSUER`` / ``KEYCLOAK_ISSUER``.`
- `Env: ``GUNDI_OAUTH_AUDIENCE`` / ``OAUTH_AUDIENCE`` / ``KEYCLOAK_AUDIENCE``.`
- `Env: ``GUNDI_OAUTH_SCOPE`` / ``OAUTH_SCOPE`` (default ``"openid"``).`

- [ ] **Step 3: Update docs, examples, and the CLI skill**

For every hit from Step 1 in `README.md`, `docs/`, `examples/`, and `.claude/skills/using-the-gundi-cli/SKILL.md`: replace `OAUTH_X` with `GUNDI_OAUTH_X` as the primary documented name. Where a page first introduces the env vars (README auth section, `docs/getting-started/auth-setup.md`, `docs/authentication/overview.md`, `examples/README.md`, the SKILL.md), add one sentence:

> The un-prefixed `OAUTH_*` names (and, for the library, the legacy `KEYCLOAK_*` names) are still accepted as fallbacks.

In `MIGRATION.md`, leave the existing 2.x → 3.0 history intact and add a short section at the top:

```markdown
## 3.7.0 — `GUNDI_OAUTH_*` env var names

The preferred env var names for OAuth configuration are now prefixed with
`GUNDI_` to avoid collisions with other tools sharing an environment:

| Old (still accepted) | New (preferred) |
|---|---|
| `OAUTH_ISSUER` | `GUNDI_OAUTH_ISSUER` |
| `OAUTH_TOKEN_URL` | `GUNDI_OAUTH_TOKEN_URL` |
| `OAUTH_CLIENT_ID` | `GUNDI_OAUTH_CLIENT_ID` |
| `OAUTH_CLIENT_SECRET` | `GUNDI_OAUTH_CLIENT_SECRET` |
| `OAUTH_AUDIENCE` | `GUNDI_OAUTH_AUDIENCE` |
| `OAUTH_SCOPE` | `GUNDI_OAUTH_SCOPE` |

No action is required: the old `OAUTH_*` names (and the pre-3.0 `KEYCLOAK_*`
names, for the library) keep working as silent fallbacks. When both spellings
are set, the `GUNDI_`-prefixed one wins.
```

Keep example `.env` snippets and shell exports runnable — they should show only the new names.

- [ ] **Step 4: Verify nothing was missed and nothing broke**

Run: `grep -rn "OAUTH_\|KEYCLOAK_" README.md MIGRATION.md docs examples .claude --include="*.md" --include="*.py" | grep -v "docs/superpowers" | grep -v "GUNDI_OAUTH" | grep -v "still accepted" | grep -v "fallback"`
Expected: no hits other than intentional back-compat mentions (eyeball the remainder).

Run: `uv run pytest`
Expected: full suite PASSES (examples aren't imported by tests, but this catches accidental code edits).

- [ ] **Step 5: Format and commit**

```bash
uv run black examples gundi_client_v2/client.py
git add README.md MIGRATION.md docs examples .claude/skills gundi_client_v2/client.py
git commit -m "docs: document GUNDI_OAUTH_* as the preferred env var names"
```

---

### Task 4: Version bump and full verification

**Files:**
- Modify: `gundi_client_v2/__init__.py:1`

**Interfaces:**
- Consumes: everything above.
- Produces: `__version__ = "3.7.0"` (hatch reads the version from this file per `pyproject.toml [tool.hatch.version]`).

- [ ] **Step 1: Bump the version**

In `gundi_client_v2/__init__.py` line 1, change `__version__ = "3.6.3"` to `__version__ = "3.7.0"`.

- [ ] **Step 2: Run the full test suite and style check**

Run: `uv run pytest && uv run black --check .`
Expected: ALL PASS, no reformatting needed.

- [ ] **Step 3: Commit**

```bash
git add gundi_client_v2/__init__.py
git commit -m "Bump version to 3.7.0"
```
