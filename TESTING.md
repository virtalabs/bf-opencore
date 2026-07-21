# Testing Guide

This document describes the testing infrastructure for blueflow: setup, fixtures, conventions, and coverage.

## Setup Instructions

### Prerequisites

- Python 3.12+
- PostgreSQL
- [uv](https://github.com/astral-sh/uv) package manager (or pip)

### Install dependencies

Install the package with dev dependencies:

```bash
uv sync --all-extras
```

Use the project's dev environment when running tests; do not rely on a global pytest that may use a different interpreter or environment.

### Database configuration

All tests require PostgreSQL. There is no SQLite fallback; `project.settings.test` raises `RuntimeError` if `DATABASE_URL` is unset.

Set the environment variable before running tests:

```bash
export DATABASE_URL=postgresql://blueflow:blueflow@localhost:5432/blueflow
```

When using docker-compose, use `postgresql://blueflow:blueflow@localhost:5432/blueflow` when the db service is exposed on localhost.

### Django settings

While root `conftest.py` sets `DJANGO_SETTINGS_MODULE` to `project.settings.test` in `pytest_configure`, scoped runs may fail due to import order.
As a workaround, set this before invoking pytest:

```bash
export DJANGO_SETTINGS_MODULE=project.settings.test
```

### Running tests

For reliable collection, set `DATABASE_URL` and `DJANGO_SETTINGS_MODULE` before running (see above).

**Run project-level tests only** (smoke tests, migrations, models, views):

```bash
uv run pytest tests/
```

**Run app-level tests only** (blueflow integration and API tests):

```bash
uv run pytest blueflow/tests/
```

**Run default tests** (both project and app; excludes `@pytest.mark.contract`):

```bash
uv run pytest tests/ blueflow/tests/
```

Or rely on the default `testpaths`:

```bash
uv run pytest
```

**Run consumer contract tests** (gated in `.github/workflows/contracts.yml`; needs Prism for Viper wire tests):

```bash
uv run pytest -m contract
```

To match CI verify (excludes oasdiff integration test): `uv run pytest -m "contract and not integration"`.

Default pytest skips contract-marked tests even if you pass a contract file path — use `-m contract` with the path.

**Run a single file:**

```bash
uv run pytest blueflow/tests/test_groups.py
```

**Run a single test:**

```bash
uv run pytest blueflow/tests/test_groups.py::test_get_groups_for_asset_new -v
```

**Faster re-runs (keep database between runs):**

```bash
uv run pytest --reuse-db tests/ blueflow/tests/
```

**Using Docker:**

```bash
docker-compose run web uv run pytest tests/ blueflow/tests/
```

---

## Fixture Patterns and Test Data Strategies

### Conftest layering

The project uses a three-tier conftest structure:

| Tier    | Path                            | Provides                                                                                                                                                 |
| ------- | ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Root    | `conftest.py`                   | `pytest_configure`, `pytest_ignore_collect`, `django_db_setup` (session-scoped PostgreSQL), `enable_core_switch` (waffle), `auth_client`, `admin_client` |
| Project | `tests/conftest.py`             | Empty; inherits root fixtures                                                                                                                            |
| App     | `blueflow/tests/conftest.py` | Role-alias clients, data fixtures                                                                                                                        |

### Root fixtures (`conftest.py`)

- **`enable_core_switch`** — Activates the `"core"` waffle switch so API views (e.g. `/assets/`) are allowed in tests.
- **`django_db_setup`** — Session-scoped; uses PostgreSQL only. Supports `--reuse-db`.
- **`auth_client`** — DRF `APIClient` authenticated with a regular user (via `make_user`).
- **`admin_client`** — DRF `APIClient` authenticated with a superuser (via `make_superuser`).

### App-level role-alias clients (`blueflow/tests/conftest.py`)

In blueflow, all role-scoped clients are aliases to `auth_client` (adds per-resource permissions):

- `asset_edit_client` — User that can create/edit assets
- `nwk_authorized_client` — User allowed to manage networks
- `biomed_client` — User with biomed role
- `custom_field_edit_client` — User allowed to edit custom field names

### App-level data fixtures (`blueflow/tests/conftest.py`)

- **`media_root`** — Uses `tmp_path` for `MEDIA_ROOT` so attachment tests don't touch the project filesystem. Use for any test that uploads files.
- **`cleandb`** — Removes migration-seeded custom field names so tests start with a clean slate.
- **`cfield`** — Depends on `cleandb`. Creates an asset, custom field names (`sparkliness`, `shinyness`), and a custom field value.
- **`asset_groups`** — Two assets, three groups, and three asset-group links (named tuple `AssetGroups`).
- **`asset_vulnerabilities`** — Two assets, four vulnerabilities, and linking records.
- **`complete_us`** — Six assets (manufacturer/model pairs) for autocomplete field tests.

### Factory module (`blueflow/tests/factories.py`)

| Helper           | Implementation              | Use                                   |
| ---------------- | --------------------------- | ------------------------------------- |
| `make_user`      | Django `create_user`        | Correct password hashing for API auth |
| `make_superuser` | Django `create_superuser`   | Admin-style tests                     |
| `make_tag`       | `model_bakery` `baker.make` | Tag creation with defaults            |

Only `make_user` and `make_superuser` are consumed by the root conftest.
Use `auth_client` or `admin_client` for API tests.
Call `make_user`/`make_superuser` directly when you need a custom user instance.

---

## Testing Conventions

### Style

- All tests are **plain functions** (no `class Test*`).
- Tests use the `db` fixture indirectly via client fixtures, which provides `@pytest.mark.django_db` semantics.
- DRF `APIClient` with `force_authenticate` — session or cookie auth is not currently used.

### Paginated responses

The API uses `HugeLimitOffsetPagination`. Assert against:

- `response.data['count']` — Total number of results
- `response.data['results']` — List of objects

### Expected failures and skips

**`@pytest.mark.xfail`** — Tests that are expected to fail:

- `reason="Blueflow has no role-based write permissions"` — Regular user gets 403 in the product; currently in blueflow, `auth_client` has full access (12 tests).
- `raises=(SomeError,)` — Tests that exercise known bugs or unimplemented features.
- `raises=(IntegrityError, TransactionManagementError)` — Tests that trigger database constraint violations.

**`@pytest.mark.skip`** — Tests that are never run:

- Routes that do not currently exist (e.g. `test_api_add_custom_field_via_asset`).

### Feature gating

All API viewsets use `WaffleSwitchMixin` with `waffle_switch = "core"`.
The `enable_core_switch` fixture activates this switch.
Both `auth_client` and `admin_client` depend on it, so it is active for all API tests.

### Pytest options

- `addopts = "-ra"` — Shows a short summary for all non-passing tests (failures, errors, skips, xfails).

---

## Coverage Goals and Reports

Coverage tooling is not yet configured. To add it:

### 1. Add pytest-cov

Add to `[project.optional-dependencies] dev` in `pyproject.toml`:

```toml
"pytest-cov",
```

Run `uv sync --all-extras` (or `uv pip install -e ".[dev]"`) to install.

### 2. Configure coverage in pyproject.toml

```toml
[tool.coverage.run]
source = ["blueflow"]
omit = [
    "*/migrations/*",
    "*/__init__.py",
    "*/tests/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
]
```

### 3. Generate a report

After completing steps 1–2 and reinstalling dependencies:

```bash
uv run pytest --cov=blueflow --cov-report=markdown tests/ blueflow/tests/
```
