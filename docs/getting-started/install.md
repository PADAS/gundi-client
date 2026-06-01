# Installation

## Prerequisites

- **Python 3.10 or newer.** Check with `python3 --version`.
- A package installer — `pip` or `uv` (recommended for speed).

## Install from PyPI

```bash
uv pip install gundi-client-v2
```

Or with plain pip:

```bash
pip install gundi-client-v2
```

Pin to a specific version with `gundi-client-v2==X.Y.Z`. The latest release
is on the [PyPI project page](https://pypi.org/project/gundi-client-v2/).

## Install from source

For development or to pin to a specific commit:

```bash
pip install "gundi-client-v2 @ git+https://github.com/PADAS/gundi-client.git@v2"
```

## Compatibility

| Package | Required |
|---|---|
| Python | `>=3.10` |
| `httpx` | `>=0.28` |
| `pydantic` | `>=1.10,<2` (pydantic v1 line) |
| `gundi-core` | `>=1.5.8,<3` |

If your app uses **FastAPI**, you'll also need `fastapi>=0.110.3` and
`starlette>=0.37` to coexist with `httpx>=0.28`. See the
[Migration guide](../migration.md) for details on the upgrade triangle.

## Verify

After installing, confirm the import succeeds:

```bash
python -c "import gundi_client_v2; print(gundi_client_v2.__version__)"
```

Expected output: the installed version number (e.g. `3.0.0`).

## Next

→ [Authentication setup](auth-setup.md) — configure credentials so the
client can talk to Gundi.
