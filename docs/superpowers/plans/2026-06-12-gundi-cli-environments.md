# Gundi CLI Named Environments + Token Cache — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent named environments (`default`, `dev`, `prod`, …) and a cross-invocation OAuth token cache to the `gundi` CLI so repeat commands don't re-authenticate each run.

**Architecture:** Two pure filesystem/serialization modules (`config_store`, `token_store`) under `~/.config/gundi/` (JSON, 0600, no secrets at rest — only derived tokens). `_client.py` gains environment resolution (precedence: `--profile` → `GUNDI_PROFILE` → active → raw env) and a run-wrapper that restores a cached token onto the `GundiClient`, runs the command, then persists a rotated token. New `gundi env` and `gundi auth` command groups sit on top.

**Tech Stack:** Python 3.10+, Typer (existing `cli` extra), `gundi_core.schemas.OAuthToken`, stdlib `json`/`pathlib`/`os`; tests with `pytest`, `respx`, Typer `CliRunner`, `tmp_path` + monkeypatched `XDG_CONFIG_HOME`.

---

## Spec reference

`docs/superpowers/specs/2026-06-12-gundi-cli-environments-design.md`

## File structure

| File | Responsibility | Action |
|------|----------------|--------|
| `gundi_client_v2/cli/config_store.py` | XDG path resolution; read/write `config.json`; environment CRUD; active selection; dir/file perms. | Create |
| `gundi_client_v2/cli/token_store.py` | Serialize/restore/delete per-env token; apply onto / detect change on a `GundiClient`. | Create |
| `gundi_client_v2/cli/_client.py` | Add environment resolution, profile-aware client build, `run_command` wrapper, login client builder. Keep raw-env `build_client`. | Modify |
| `gundi_client_v2/cli/env.py` | `gundi env add/list/show/use/remove`. | Create |
| `gundi_client_v2/cli/auth.py` | `gundi auth login/logout/status`. | Create |
| `gundi_client_v2/cli/integrations.py` | Add `--profile` option; route through `run_command`. | Modify |
| `gundi_client_v2/cli/main.py` | Register `env` and `auth` sub-apps. | Modify |
| `tests/test_cli_config_store.py` | config_store unit tests. | Create |
| `tests/test_cli_token_store.py` | token_store unit tests. | Create |
| `tests/test_cli_env.py` | `gundi env` command tests. | Create |
| `tests/test_cli_auth.py` | `gundi auth` command tests. | Create |
| `tests/test_cli.py` | Extend with profile precedence + token-reuse tests. | Modify |
| `README.md` | Document environments + token cache. | Modify |

Conventions to follow (from existing tests): `respx.mock(assert_all_called=False)`, `CliRunner()` from `typer.testing`, fixtures `auth_token_response` / `destination_integration_details` in `tests/conftest.py`. Run tests with `.venv/bin/python -m pytest`. Format new files with `.venv/bin/black <files>`.

---

## Task 1: config_store — paths, load/save, permissions

**Files:**
- Create: `gundi_client_v2/cli/config_store.py`
- Test: `tests/test_cli_config_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_config_store.py
import json
import os
import stat

import pytest

from gundi_client_v2.cli import config_store


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def test_config_dir_under_xdg(tmp_path):
    assert config_store.config_dir() == tmp_path / "gundi"


def test_load_config_missing_returns_empty():
    assert config_store.load_config() == {"active": None, "environments": {}}


def test_save_then_load_round_trips():
    config_store.save_config({"active": "prod", "environments": {"prod": {"base_url": "u"}}})
    assert config_store.load_config() == {"active": "prod", "environments": {"prod": {"base_url": "u"}}}


def test_save_config_sets_0600_and_dir_0700(tmp_path):
    config_store.save_config({"active": None, "environments": {}})
    cfg = config_store.config_file()
    assert stat.S_IMODE(cfg.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "gundi").stat().st_mode) == 0o700


def test_load_config_corrupt_raises_config_error():
    config_store.config_dir().mkdir(parents=True)
    config_store.config_file().write_text("{not json")
    with pytest.raises(config_store.ConfigError):
        config_store.load_config()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli_config_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'gundi_client_v2.cli.config_store'`

- [ ] **Step 3: Write minimal implementation**

```python
# gundi_client_v2/cli/config_store.py
"""Persistent CLI configuration: named environments stored under XDG config.

Stores only non-secret connection config in ``config.json``. Secrets are never
written here (see token_store for cached tokens). All files are user-private.
"""

import json
import os
from pathlib import Path
from typing import Optional


class ConfigError(Exception):
    """Raised for missing/unknown environments or unreadable config."""


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "gundi"


def config_file() -> Path:
    return config_dir() / "config.json"


def tokens_dir() -> Path:
    return config_dir() / "tokens"


def ensure_dir(path: Path) -> None:
    """Create ``path`` (and parents) private to the user (0700)."""
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def load_config() -> dict:
    path = config_file()
    if not path.exists():
        return {"active": None, "environments": {}}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigError(f"could not read config at {path}: {exc}")


def save_config(config: dict) -> None:
    ensure_dir(config_dir())
    path = config_file()
    path.write_text(json.dumps(config, indent=2))
    os.chmod(path, 0o600)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cli_config_store.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add gundi_client_v2/cli/config_store.py tests/test_cli_config_store.py
git commit -m "Add config_store: XDG paths, load/save, private perms"
```

---

## Task 2: config_store — environment CRUD + active selection

**Files:**
- Modify: `gundi_client_v2/cli/config_store.py`
- Test: `tests/test_cli_config_store.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_cli_config_store.py
def test_add_get_environment():
    config_store.add_environment("dev", {"base_url": "u", "client_id": "c"})
    assert config_store.get_environment("dev") == {"base_url": "u", "client_id": "c"}


def test_add_first_environment_does_not_auto_activate():
    config_store.add_environment("dev", {"base_url": "u"})
    assert config_store.get_active() is None


def test_get_unknown_environment_raises():
    with pytest.raises(config_store.ConfigError):
        config_store.get_environment("nope")


def test_set_active_requires_existing():
    with pytest.raises(config_store.ConfigError):
        config_store.set_active("ghost")


def test_set_and_get_active():
    config_store.add_environment("prod", {"base_url": "u"})
    config_store.set_active("prod")
    assert config_store.get_active() == "prod"


def test_list_environments():
    config_store.add_environment("a", {"base_url": "u"})
    config_store.add_environment("b", {"base_url": "u"})
    assert set(config_store.list_environments()) == {"a", "b"}


def test_remove_environment_clears_active_when_removed():
    config_store.add_environment("a", {"base_url": "u"})
    config_store.set_active("a")
    config_store.remove_environment("a")
    assert "a" not in config_store.list_environments()
    assert config_store.get_active() is None


def test_remove_unknown_raises():
    with pytest.raises(config_store.ConfigError):
        config_store.remove_environment("nope")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cli_config_store.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'add_environment'`

- [ ] **Step 3: Implement**

```python
# append to gundi_client_v2/cli/config_store.py
def add_environment(name: str, env: dict) -> None:
    config = load_config()
    config.setdefault("environments", {})[name] = env
    save_config(config)


def get_environment(name: str) -> dict:
    env = load_config().get("environments", {}).get(name)
    if env is None:
        raise ConfigError(f"unknown environment '{name}'")
    return env


def list_environments() -> dict:
    return load_config().get("environments", {})


def set_active(name: str) -> None:
    config = load_config()
    if name not in config.get("environments", {}):
        raise ConfigError(f"unknown environment '{name}'")
    config["active"] = name
    save_config(config)


def get_active() -> Optional[str]:
    return load_config().get("active")


def remove_environment(name: str) -> None:
    config = load_config()
    if name not in config.get("environments", {}):
        raise ConfigError(f"unknown environment '{name}'")
    del config["environments"][name]
    if config.get("active") == name:
        config["active"] = None
    save_config(config)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_cli_config_store.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add gundi_client_v2/cli/config_store.py tests/test_cli_config_store.py
git commit -m "Add environment CRUD + active selection to config_store"
```

---

## Task 3: token_store — persist/restore cached tokens

**Files:**
- Create: `gundi_client_v2/cli/token_store.py`
- Test: `tests/test_cli_token_store.py`

Relies on `GundiClient` public attributes `cached_token` (an `OAuthToken`), `cached_token_expires_at`, `cached_token_refresh_expires_at` (both tz-aware datetimes), confirmed in `gundi_client_v2/client.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_token_store.py
import stat
from datetime import datetime, timedelta, timezone

import pytest

from gundi_client_v2.cli import token_store


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


class FakeToken:
    def __init__(self, access, refresh="r", token_type="Bearer"):
        self.access_token = access
        self.refresh_token = refresh
        self.token_type = token_type
        self.expires_in = 0
        self.refresh_expires_in = 0


class FakeClient:
    def __init__(self):
        self.cached_token = None
        self.cached_token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self.cached_token_refresh_expires_at = datetime.min.replace(tzinfo=timezone.utc)


def _future(seconds):
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def test_save_then_load_round_trips():
    exp, rexp = _future(1800), _future(43200)
    token_store.save_token("prod", FakeToken("AT", "RT"), exp, rexp)
    data = token_store.load_token("prod")
    assert data["access_token"] == "AT"
    assert data["refresh_token"] == "RT"
    assert datetime.fromisoformat(data["expires_at"]) == exp


def test_token_file_is_0600():
    token_store.save_token("prod", FakeToken("AT"), _future(60), _future(60))
    assert stat.S_IMODE(token_store.token_file("prod").stat().st_mode) == 0o600


def test_load_missing_returns_none():
    assert token_store.load_token("prod") is None


def test_load_corrupt_returns_none():
    token_store.config_store.ensure_dir(token_store.config_store.tokens_dir())
    token_store.token_file("prod").write_text("{bad")
    assert token_store.load_token("prod") is None


def test_delete_token():
    token_store.save_token("prod", FakeToken("AT"), _future(60), _future(60))
    assert token_store.delete_token("prod") is True
    assert token_store.load_token("prod") is None
    assert token_store.delete_token("prod") is False


def test_apply_to_client_restores_attributes():
    exp, rexp = _future(1800), _future(43200)
    token_store.save_token("prod", FakeToken("AT", "RT"), exp, rexp)
    client = FakeClient()
    token_store.apply_to_client(client, token_store.load_token("prod"))
    assert client.cached_token.access_token == "AT"
    assert client.cached_token_expires_at == exp
    assert client.cached_token_refresh_expires_at == rexp
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cli_token_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'gundi_client_v2.cli.token_store'`

- [ ] **Step 3: Implement**

```python
# gundi_client_v2/cli/token_store.py
"""Per-environment OAuth token cache.

Persists tokens derived from a login so subsequent CLI invocations reuse them
instead of re-authenticating. One file per environment under
``<config>/tokens/<env>.json`` (0600). Secrets are never stored here.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from gundi_core.schemas import OAuthToken

from . import config_store


def token_file(env_name: str) -> Path:
    return config_store.tokens_dir() / f"{env_name}.json"


def save_token(env_name, token, expires_at: datetime, refresh_expires_at: datetime) -> None:
    config_store.ensure_dir(config_store.tokens_dir())
    payload = {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "token_type": token.token_type,
        "expires_at": expires_at.isoformat(),
        "refresh_expires_at": refresh_expires_at.isoformat(),
    }
    path = token_file(env_name)
    path.write_text(json.dumps(payload, indent=2))
    os.chmod(path, 0o600)


def load_token(env_name) -> Optional[dict]:
    path = token_file(env_name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None  # corrupt cache == miss; caller falls back to re-auth


def delete_token(env_name) -> bool:
    path = token_file(env_name)
    if path.exists():
        path.unlink()
        return True
    return False


def apply_to_client(client, data: dict) -> None:
    """Restore a cached token onto a GundiClient so it skips re-authentication.

    Sets ``cached_token`` plus the two absolute expiry timestamps directly, so
    the client treats the token as live until it actually expires.
    """
    client.cached_token = OAuthToken(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", ""),
        token_type=data.get("token_type", "Bearer"),
        expires_in=0,
        refresh_expires_in=0,
    )
    client.cached_token_expires_at = datetime.fromisoformat(data["expires_at"])
    client.cached_token_refresh_expires_at = datetime.fromisoformat(data["refresh_expires_at"])
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_cli_token_store.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add gundi_client_v2/cli/token_store.py tests/test_cli_token_store.py
git commit -m "Add token_store: persist/restore cached OAuth tokens"
```

---

## Task 4: _client.py — environment resolution + run_command + login builder

**Files:**
- Modify: `gundi_client_v2/cli/_client.py`
- Test: `tests/test_cli.py` (extend)

This task adds the profile-aware plumbing. Behavior to implement:
- `resolve_environment(profile)` — precedence `--profile` → `GUNDI_PROFILE` → stored active → `None` (raw env). Validates a named env exists (raises `ConfigError`).
- `active_env_name(profile)` — like above but for `auth`/`env` commands that require a profile; exits 2 when none selected.
- `_build_profile_client(env)` — `GundiClient` from non-secret config plus any secrets present in env vars (enables implicit auth and client-credentials refresh).
- `build_client_for_login(env_name)` — config + secret obtained from env or hidden prompt (grant chosen by presence of `username`).
- `run_command(profile, async_fn)` — resolve env, restore cached token, run, persist rotated token, map errors (profile path suggests `gundi auth login` on auth failure).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_cli.py  (imports already include json, httpx, respx, runner, app)
from gundi_client_v2.cli import config_store, token_store  # add near top imports


def test_resolve_environment_precedence(tmp_path, monkeypatch):
    from gundi_client_v2.cli import _client
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config_store.add_environment("dev", {"base_url": "u", "client_id": "c"})
    config_store.add_environment("prod", {"base_url": "u", "client_id": "c"})
    config_store.set_active("prod")

    # stored active wins when nothing else given
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    assert _client.resolve_environment(None) == "prod"
    # GUNDI_PROFILE beats active
    monkeypatch.setenv("GUNDI_PROFILE", "dev")
    assert _client.resolve_environment(None) == "dev"
    # explicit flag beats env var
    assert _client.resolve_environment("prod") == "prod"


def test_resolve_environment_none_without_config(tmp_path, monkeypatch):
    from gundi_client_v2.cli import _client
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    assert _client.resolve_environment(None) is None


def test_resolve_environment_unknown_raises(tmp_path, monkeypatch):
    from gundi_client_v2.cli import _client
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(config_store.ConfigError):
        _client.resolve_environment("ghost")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k resolve_environment -q`
Expected: FAIL — `AttributeError: module 'gundi_client_v2.cli._client' has no attribute 'resolve_environment'`

- [ ] **Step 3: Implement (add to `_client.py`)**

Add imports at the top of `_client.py` (after the existing imports):

```python
from typing import Optional

from gundi_core.schemas import OAuthToken

from . import config_store, token_store
```

Then append:

```python
def resolve_environment(profile: Optional[str]) -> Optional[str]:
    """Resolve the active environment name, or None to use raw env vars.

    Precedence: explicit ``profile`` > ``GUNDI_PROFILE`` > stored active > None.
    Raises ConfigError if a named environment does not exist.
    """
    name = profile or os.environ.get("GUNDI_PROFILE") or config_store.get_active()
    if name:
        config_store.get_environment(name)  # validate; raises ConfigError
    return name


def active_env_name(profile: Optional[str]) -> str:
    """Like resolve_environment, but for commands that require a profile.

    Exits 2 with guidance when no environment is selected.
    """
    name = profile or os.environ.get("GUNDI_PROFILE") or config_store.get_active()
    if not name:
        typer.echo(
            "Error: no environment selected. Run `gundi env use <name>` or pass --profile.",
            err=True,
        )
        raise typer.Exit(2)
    config_store.get_environment(name)  # validate; raises ConfigError
    return name


def _client_kwargs_from_env(env: dict) -> dict:
    kwargs = {"base_url": env["base_url"], "oauth_client_id": env["client_id"]}
    if v := env.get("issuer"):
        kwargs["oauth_issuer"] = v
    if v := env.get("token_url"):
        kwargs["oauth_token_url"] = v
    if v := env.get("audience"):
        kwargs["oauth_audience"] = v
    if v := env.get("username"):
        kwargs["username"] = v
    if v := env.get("scope"):
        kwargs["oauth_scope"] = v
    return kwargs


def _build_profile_client(env: dict) -> GundiClient:
    """Client from a profile's config, plus any secrets available in env vars.

    Supplying env secrets (when present) lets the client authenticate implicitly
    on a cache miss and refresh client-credentials tokens; they are optional.
    """
    kwargs = _client_kwargs_from_env(env)
    if env.get("username") and (pw := os.environ.get("GUNDI_PASSWORD")):
        kwargs["password"] = pw
    if secret := os.environ.get("OAUTH_CLIENT_SECRET"):
        kwargs["oauth_client_secret"] = secret
    return GundiClient(**kwargs)


def build_client_for_login(env_name: str) -> GundiClient:
    """Client for `gundi auth login`: config + a secret from env or a hidden prompt.

    Grant is chosen by the profile: a stored ``username`` means password grant
    (prompt for password); otherwise client-credentials (prompt for secret).
    """
    env = config_store.get_environment(env_name)
    kwargs = _client_kwargs_from_env(env)
    if env.get("username"):
        kwargs["password"] = os.environ.get("GUNDI_PASSWORD") or typer.prompt(
            "Password", hide_input=True
        )
    else:
        kwargs["oauth_client_secret"] = os.environ.get("OAUTH_CLIENT_SECRET") or typer.prompt(
            "Client secret", hide_input=True
        )
    return GundiClient(**kwargs)


def run_command(profile: Optional[str], async_fn: Callable[[GundiClient], Awaitable[T]]) -> T:
    """Resolve the environment, restore any cached token, run, persist, map errors."""
    try:
        env_name = resolve_environment(profile)
    except config_store.ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2)

    if env_name is None:
        # Backward-compatible raw-env path (no profile configured).
        return run_with_client(async_fn)

    client = _build_profile_client(config_store.get_environment(env_name))
    cached = token_store.load_token(env_name)
    if cached:
        token_store.apply_to_client(client, cached)
    had_token = client.cached_token is not None
    before = client.cached_token.access_token if client.cached_token else None

    async def _runner() -> T:
        async with client:
            return await async_fn(client)

    try:
        result = asyncio.run(_runner())
    except AuthenticationError:
        suffix = f" --profile {env_name}" if profile else ""
        typer.echo(
            f"Error: not authenticated for '{env_name}'. Run `gundi auth login{suffix}`.",
            err=True,
        )
        raise typer.Exit(1)
    except GundiAPIError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    # Persist a newly obtained or rotated token.
    if client.cached_token and (not had_token or client.cached_token.access_token != before):
        token_store.save_token(
            env_name,
            client.cached_token,
            client.cached_token_expires_at,
            client.cached_token_refresh_expires_at,
        )
    return result
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k resolve_environment -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full CLI test file (no regressions)**

Run: `.venv/bin/python -m pytest tests/test_cli.py -q`
Expected: PASS (all existing + 3 new)

- [ ] **Step 6: Commit**

```bash
git add gundi_client_v2/cli/_client.py tests/test_cli.py
git commit -m "Add environment resolution, profile client, run_command to _client"
```

---

## Task 5: `gundi env` commands

**Files:**
- Create: `gundi_client_v2/cli/env.py`
- Test: `tests/test_cli_env.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_env.py
import pytest
from typer.testing import CliRunner

from gundi_client_v2.cli import app, config_store

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    return tmp_path


def test_env_add_stores_environment():
    result = runner.invoke(
        app,
        ["env", "add", "prod", "--base-url", "https://api.x", "--client-id", "c",
         "--issuer", "https://auth.x"],
    )
    assert result.exit_code == 0, result.output
    env = config_store.get_environment("prod")
    assert env == {"base_url": "https://api.x", "client_id": "c", "issuer": "https://auth.x"}


def test_env_add_requires_issuer_or_token_url():
    result = runner.invoke(
        app, ["env", "add", "prod", "--base-url", "u", "--client-id", "c"]
    )
    assert result.exit_code == 2, result.output
    assert "--issuer" in result.output


def test_env_add_activate_sets_active():
    runner.invoke(
        app, ["env", "add", "prod", "--base-url", "u", "--client-id", "c",
               "--issuer", "i", "--activate"]
    )
    assert config_store.get_active() == "prod"


def test_env_use_and_list_marks_active():
    runner.invoke(app, ["env", "add", "a", "--base-url", "u", "--client-id", "c", "--issuer", "i"])
    runner.invoke(app, ["env", "add", "b", "--base-url", "u", "--client-id", "c", "--issuer", "i"])
    runner.invoke(app, ["env", "use", "b"])
    result = runner.invoke(app, ["env", "list"])
    assert result.exit_code == 0
    assert "* b" in result.output
    assert "  a" in result.output


def test_env_use_unknown_exits_2():
    result = runner.invoke(app, ["env", "use", "ghost"])
    assert result.exit_code == 2
    assert "unknown environment" in result.output


def test_env_show_outputs_config():
    runner.invoke(app, ["env", "add", "prod", "--base-url", "u", "--client-id", "c", "--issuer", "i"])
    result = runner.invoke(app, ["env", "show", "prod"])
    assert result.exit_code == 0
    assert "base_url" in result.output


def test_env_remove_deletes():
    runner.invoke(app, ["env", "add", "prod", "--base-url", "u", "--client-id", "c", "--issuer", "i"])
    result = runner.invoke(app, ["env", "remove", "prod"])
    assert result.exit_code == 0
    assert "prod" not in config_store.list_environments()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cli_env.py -q`
Expected: FAIL — `env` is not a registered command (Typer usage error / non-zero exit on `env add`).

- [ ] **Step 3: Implement**

```python
# gundi_client_v2/cli/env.py
"""`gundi env` commands: manage named environments."""

import json
from typing import Optional

import typer

from . import config_store, token_store

env_app = typer.Typer(help="Manage named Gundi environments.", no_args_is_help=True)


@env_app.command("add")
def add_env(
    name: str = typer.Argument(..., help="Environment name (e.g. prod, dev)."),
    base_url: str = typer.Option(..., "--base-url", help="Gundi API base URL."),
    client_id: str = typer.Option(..., "--client-id", help="OAuth client id."),
    issuer: Optional[str] = typer.Option(None, "--issuer", help="OIDC issuer URL (discovery)."),
    token_url: Optional[str] = typer.Option(None, "--token-url", help="Explicit OAuth token URL."),
    audience: Optional[str] = typer.Option(None, "--audience", help="OAuth audience."),
    username: Optional[str] = typer.Option(None, "--username", help="Username (password grant)."),
    scope: Optional[str] = typer.Option(None, "--scope", help="OAuth scope."),
    activate: bool = typer.Option(False, "--activate", help="Make this the active environment."),
) -> None:
    """Add or overwrite a named environment."""
    if not issuer and not token_url:
        typer.echo("Error: provide --issuer or --token-url.", err=True)
        raise typer.Exit(2)
    env = {"base_url": base_url, "client_id": client_id}
    for key, value in (
        ("issuer", issuer),
        ("token_url", token_url),
        ("audience", audience),
        ("username", username),
        ("scope", scope),
    ):
        if value:
            env[key] = value
    config_store.add_environment(name, env)
    if activate:
        config_store.set_active(name)
    typer.echo(f"Environment '{name}' saved.")


@env_app.command("list")
def list_envs() -> None:
    """List environments; the active one is marked with `*`."""
    config = config_store.load_config()
    environments = config.get("environments", {})
    if not environments:
        typer.echo("No environments configured.", err=True)
        return
    active = config.get("active")
    for name in environments:
        typer.echo(f"{'*' if name == active else ' '} {name}")


@env_app.command("show")
def show_env(
    name: Optional[str] = typer.Argument(None, help="Environment to show (default: active)."),
) -> None:
    """Print one environment's config (no secrets are stored)."""
    try:
        target = name or config_store.get_active()
        if not target:
            typer.echo("Error: no environment specified or active.", err=True)
            raise typer.Exit(2)
        env = config_store.get_environment(target)
    except config_store.ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2)
    typer.echo(json.dumps(env, indent=2))


@env_app.command("use")
def use_env(name: str = typer.Argument(..., help="Environment to activate.")) -> None:
    """Set the active environment."""
    try:
        config_store.set_active(name)
    except config_store.ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2)
    typer.echo(f"Active environment set to '{name}'.")


@env_app.command("remove")
def remove_env(name: str = typer.Argument(..., help="Environment to remove.")) -> None:
    """Remove an environment and its cached token."""
    try:
        config_store.remove_environment(name)
    except config_store.ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2)
    token_store.delete_token(name)
    typer.echo(f"Environment '{name}' removed.")
```

Register it in `main.py` (Step 4 below) before running tests.

- [ ] **Step 4: Wire into `main.py`**

Modify `gundi_client_v2/cli/main.py` to add the import and registration:

```python
"""Typer application wiring for the `gundi` CLI."""

import typer

from .env import env_app
from .integrations import integrations_app

app = typer.Typer(
    help="Command-line interface for the Gundi API.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(integrations_app, name="integrations")
app.add_typer(env_app, name="env")
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_cli_env.py -q`
Expected: PASS (7 passed)

- [ ] **Step 6: Commit**

```bash
git add gundi_client_v2/cli/env.py gundi_client_v2/cli/main.py tests/test_cli_env.py
git commit -m "Add `gundi env` commands (add/list/show/use/remove)"
```

---

## Task 6: `gundi auth` commands

**Files:**
- Create: `gundi_client_v2/cli/auth.py`
- Modify: `gundi_client_v2/cli/main.py`
- Test: `tests/test_cli_auth.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_auth.py
import httpx
import pytest
import respx
from typer.testing import CliRunner

from gundi_client_v2.cli import app, config_store, token_store

runner = CliRunner()

ISSUER = "https://fakeauth.com/auth/realms/dev"
TOKEN_URL = f"{ISSUER}/protocol/openid-connect/token"


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    for var in ("OAUTH_CLIENT_SECRET", "GUNDI_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def _add_cc_env():
    config_store.add_environment(
        "prod", {"base_url": "https://api.x", "client_id": "c", "token_url": TOKEN_URL}
    )
    config_store.set_active("prod")


def test_login_caches_token_from_env_secret(auth_token_response, monkeypatch):
    _add_cc_env()
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "shhh")
    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        result = runner.invoke(app, ["auth", "login"])
    assert result.exit_code == 0, result.output
    assert token_store.load_token("prod") is not None


def test_login_without_secret_prompts(auth_token_response):
    _add_cc_env()
    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        result = runner.invoke(app, ["auth", "login"], input="prompted-secret\n")
    assert result.exit_code == 0, result.output
    assert token_store.load_token("prod") is not None


def test_logout_deletes_token(auth_token_response, monkeypatch):
    _add_cc_env()
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "shhh")
    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).respond(status_code=httpx.codes.OK, json=auth_token_response)
        runner.invoke(app, ["auth", "login"])
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert token_store.load_token("prod") is None


def test_status_reports_not_authenticated():
    _add_cc_env()
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 0
    assert "not authenticated" in result.output.lower()


def test_login_no_active_env_exits_2():
    result = runner.invoke(app, ["auth", "login"])
    assert result.exit_code == 2
    assert "no environment selected" in result.output.lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cli_auth.py -q`
Expected: FAIL — `auth` not registered.

- [ ] **Step 3: Implement**

```python
# gundi_client_v2/cli/auth.py
"""`gundi auth` commands: login (cache a token), logout, status."""

import asyncio
from datetime import datetime, timezone
from typing import Optional

import typer

from gundi_client_v2.errors import AuthenticationError, GundiAPIError

from . import token_store
from ._client import active_env_name, build_client_for_login

auth_app = typer.Typer(help="Authenticate and manage cached tokens.", no_args_is_help=True)


@auth_app.command("login")
def login(
    profile: Optional[str] = typer.Option(None, "--profile", help="Environment to log in to."),
) -> None:
    """Obtain and cache an OAuth token for the selected environment."""
    env_name = active_env_name(profile)
    client = build_client_for_login(env_name)

    async def _authenticate():
        async with client:
            await client.get_access_token(force_refresh_token=True)

    try:
        asyncio.run(_authenticate())
    except (AuthenticationError, GundiAPIError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    token_store.save_token(
        env_name,
        client.cached_token,
        client.cached_token_expires_at,
        client.cached_token_refresh_expires_at,
    )
    typer.echo(f"Authenticated. Token cached for '{env_name}'.")


@auth_app.command("logout")
def logout(
    profile: Optional[str] = typer.Option(None, "--profile", help="Environment to log out of."),
) -> None:
    """Delete the cached token for the selected environment."""
    env_name = active_env_name(profile)
    typer.echo("Logged out." if token_store.delete_token(env_name) else "No cached token.")


@auth_app.command("status")
def status(
    profile: Optional[str] = typer.Option(None, "--profile", help="Environment to check."),
) -> None:
    """Report whether a valid cached token exists."""
    env_name = active_env_name(profile)
    data = token_store.load_token(env_name)
    if not data:
        typer.echo(f"{env_name}: not authenticated")
        return
    expires_at = datetime.fromisoformat(data["expires_at"])
    state = "valid" if expires_at > datetime.now(timezone.utc) else "expired"
    typer.echo(f"{env_name}: {state} (access token expires {expires_at.isoformat()})")
```

- [ ] **Step 4: Wire into `main.py`**

Modify `gundi_client_v2/cli/main.py` to import and register `auth_app`:

```python
"""Typer application wiring for the `gundi` CLI."""

import typer

from .auth import auth_app
from .env import env_app
from .integrations import integrations_app

app = typer.Typer(
    help="Command-line interface for the Gundi API.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(integrations_app, name="integrations")
app.add_typer(env_app, name="env")
app.add_typer(auth_app, name="auth")
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_cli_auth.py -q`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add gundi_client_v2/cli/auth.py gundi_client_v2/cli/main.py tests/test_cli_auth.py
git commit -m "Add `gundi auth` commands (login/logout/status)"
```

---

## Task 7: Route `integrations` commands through profiles + token cache

**Files:**
- Modify: `gundi_client_v2/cli/integrations.py`
- Test: `tests/test_cli.py` (extend)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_cli.py
def test_list_uses_cached_token_no_token_post(
    tmp_path, monkeypatch, destination_integration_details
):
    # A valid cached token must be reused: NO token POST should occur.
    from datetime import datetime, timedelta, timezone
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    config_store.add_environment(
        "prod", {"base_url": BASE_URL, "client_id": "c", "token_url": TOKEN_URL}
    )
    config_store.set_active("prod")

    class _Tok:
        access_token = "CACHED"
        refresh_token = "R"
        token_type = "Bearer"
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    token_store.save_token("prod", _Tok(), future, future)

    with respx.mock(assert_all_called=False) as mock:
        # NOTE: deliberately do NOT mock the token endpoint.
        integrations_route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )
        result = runner.invoke(app, ["integrations", "list"])

    assert result.exit_code == 0, result.output
    assert destination_integration_details["id"] in result.output
    assert integrations_route.called
    # The Authorization header carried the cached token.
    assert integrations_route.calls.last.request.headers["authorization"] == "Bearer CACHED"


def test_list_profile_flag_overrides_active(
    tmp_path, monkeypatch, destination_integration_details
):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    config_store.add_environment("prod", {"base_url": BASE_URL, "client_id": "c", "token_url": TOKEN_URL})
    config_store.add_environment("dev", {"base_url": BASE_URL, "client_id": "c", "token_url": TOKEN_URL})
    config_store.set_active("prod")

    class _Tok:
        access_token = "DEVTOK"
        refresh_token = "R"
        token_type = "Bearer"
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    token_store.save_token("dev", _Tok(), future, future)

    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(INTEGRATIONS_URL).respond(
            status_code=httpx.codes.OK,
            json={"results": [destination_integration_details], "next": None},
        )
        result = runner.invoke(app, ["integrations", "list", "--profile", "dev"])

    assert result.exit_code == 0, result.output
    assert route.calls.last.request.headers["authorization"] == "Bearer DEVTOK"


def test_list_unknown_profile_exits_2(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GUNDI_PROFILE", raising=False)
    result = runner.invoke(app, ["integrations", "list", "--profile", "ghost"])
    assert result.exit_code == 2, result.output
    assert "unknown environment" in result.output
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k "cached_token or profile_flag or unknown_profile" -q`
Expected: FAIL — `integrations list` has no `--profile` option (Typer usage error, exit 2 but wrong message) / token not reused.

- [ ] **Step 3: Implement — update `integrations.py`**

Change the import line:

```python
from ._client import run_command
```

Update `list_integrations` to accept `--profile` and use `run_command`:

```python
@integrations_app.command("list")
def list_integrations(
    integration_type: Optional[str] = typer.Option(
        None, "--type", help="Filter by integration type slug (e.g. earth_ranger)."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit JSON instead of a table (pipe to jq)."
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Environment to use (overrides the active one)."
    ),
) -> None:
    """List integrations, optionally filtered by type."""
    params = {"type": integration_type} if integration_type else None

    async def _fetch(client):
        return [i async for i in client.get_integrations(params=params)]

    integrations = run_command(profile, _fetch)

    if json_output:
        typer.echo(json.dumps([i.dict() for i in integrations], default=str, indent=2))
        return
    if not integrations:
        typer.echo("No integrations found.", err=True)
        return
    typer.echo(_render_table(integrations))
```

Update `enable_integration`, `disable_integration`, and `_set_enabled` to thread `profile`:

```python
@integrations_app.command("enable")
def enable_integration(
    integration_id: str = typer.Argument(..., help="UUID of the integration to enable."),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Environment to use (overrides the active one)."
    ),
) -> None:
    """Enable an integration."""
    _set_enabled(integration_id, True, profile)


@integrations_app.command("disable")
def disable_integration(
    integration_id: str = typer.Argument(..., help="UUID of the integration to disable."),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Environment to use (overrides the active one)."
    ),
) -> None:
    """Disable an integration."""
    _set_enabled(integration_id, False, profile)


def _set_enabled(integration_id: str, enabled: bool, profile: Optional[str]) -> None:
    async def _update(client):
        return await client.update_integration(integration_id, {"enabled": enabled})

    integration = run_command(profile, _update)
    state = "enabled" if integration.enabled else "disabled"
    typer.echo(f"Integration {integration.id} ({integration.name}) is now {state}.")
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_cli.py -q`
Expected: PASS (all CLI tests, including the new three)

- [ ] **Step 5: Commit**

```bash
git add gundi_client_v2/cli/integrations.py tests/test_cli.py
git commit -m "Route integrations commands through profiles + token cache"
```

---

## Task 8: Full suite, format, README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all tests, no regressions)

- [ ] **Step 2: Format new/changed files**

Run:
```bash
.venv/bin/black gundi_client_v2/cli tests/test_cli.py tests/test_cli_config_store.py tests/test_cli_token_store.py tests/test_cli_env.py tests/test_cli_auth.py -q
```

- [ ] **Step 3: Add a README subsection** under the existing "Command-Line Interface" section, after the exit-codes paragraph:

````markdown
### Named environments

Instead of exporting auth env vars each time, save named environments and switch
between them. Config lives in `~/.config/gundi/config.json` (mode 0600);
**secrets are never written** — only the OAuth tokens derived from them, cached
per environment under `~/.config/gundi/tokens/`.

```bash
# Add environments (connection config only — no secrets)
gundi env add prod --base-url https://api.gundi.example.com \
  --client-id my-client --issuer https://auth.example.com/realms/prod
gundi env add dev  --base-url https://api.dev.example.com \
  --client-id my-client --issuer https://auth.example.com/realms/dev --username me@example.com

gundi env use prod          # set the active environment
gundi env list              # '*' marks the active one
gundi env show prod

# Authenticate once; the token is cached and reused by later commands.
# The secret/password is read from env (OAUTH_CLIENT_SECRET / GUNDI_PASSWORD)
# or prompted (hidden) — and never stored.
gundi auth login
gundi auth status
gundi integrations list     # reuses the cached token; no re-auth

# Override the active environment per command:
gundi integrations list --profile dev
gundi auth logout
```

**Environment selection precedence:** `--profile` flag → `GUNDI_PROFILE` env var
→ stored active environment → raw `OAUTH_*` / `GUNDI_*` env vars (the original
behavior, used when no environments are configured).

**Token refresh:** password-grant environments refresh transparently using the
cached refresh token. Client-credentials environments (no refresh token) require
`gundi auth login` again once the access token expires.
````

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Document named environments + token cache in README"
```

- [ ] **Step 5: Push**

```bash
git push
```

---

## Self-review notes

- **Spec coverage:** storage layout (Tasks 1,3), no-secrets-at-rest (Tasks 3,6 — login reads secret from env/prompt, only token persisted), grant-type refresh tradeoff (Task 4 `_build_profile_client` supplies env secrets for refresh; documented Task 8), precedence (Task 4 + Task 7 tests), `gundi env` (Task 5), `gundi auth` (Task 6), integrations reuse + implicit fallback (Task 4 `run_command` + Task 7), exit codes (Tasks 5–7), corrupt-file handling (Tasks 1,3), the "valid cached token ⇒ no token POST" guarantee (Task 7 test). All covered.
- **Type consistency:** `config_store.ensure_dir` (public, used by token_store), `add_environment/get_environment/list_environments/set_active/get_active/remove_environment`, `token_store.save_token(env, token, expires_at, refresh_expires_at)` / `load_token` / `delete_token` / `apply_to_client`, `_client.resolve_environment/active_env_name/build_client_for_login/run_command` — names consistent across tasks.
- **No placeholders:** every code/test step contains complete code and exact commands.
