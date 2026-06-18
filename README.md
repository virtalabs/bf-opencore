# blueflow

Blueflow Django app. Installable package containing the **blueflow** Django application.

## Prerequisites

- Python 3.12+
- PostgreSQL (required — SQLite is not supported)
- [uv](https://github.com/astral-sh/uv)

## App identity

- **blueflow** is the installable Django app.
  - Add it to any Django project via `INSTALLED_APPS`:
    ```python
    INSTALLED_APPS = [
        ...
        'blueflow',  # or 'blueflow.apps.BlueflowConfig'
    ]
    ```
  - Wire up its URLs in your project's `urls.py`:
    ```python
    path('api/', include('blueflow.urls')),
    ```
  - The main BlueFlow product (e.g. blueflow-saas) consumes blueflow as a dependency.

- **Standalone run:** The minimal Django project in `project/` lets you run blueflow by itself with no other repo:
  - `docker-compose up`, or
  - `python project/manage.py runserver`

## Install

```bash
uv pip install -e .
```

Or with optional dev dependencies:

```bash
uv pip install -e ".[dev]"
```

## Running tests

**Prerequisites:**

- Install dev dependencies: `uv sync --all-extras`
- Set `DATABASE_URL` to a live PostgreSQL instance:
  ```bash
  export DATABASE_URL=postgresql://blueflow:blueflow@localhost:5432/blueflow
  ```
- Test settings are applied automatically via `pytest.ini` / `conftest.py` — no manual `DJANGO_SETTINGS_MODULE` needed.

**Test layout**

- **`tests/`** (project-level): Smoke and functional tests for the minimal project (schema, URL wiring, migrations). This is the default `pytest` collection target.
- **`blueflow/tests/`** (app-level): Integration and functional tests for the blueflow app.

**Run default tests** (excludes `@pytest.mark.contract`; see `contracts.yml` for contract lane)

```bash
uv run pytest
```

**Run contract tests**

```bash
uv run pytest -m contract
```

**Run only project-level tests**

```bash
uv run pytest tests/
```

**Run only app-level tests**

```bash
uv run pytest blueflow/tests/
```

**Run via Docker**

```bash
docker-compose run web uv run pytest
```

## Running blueflow standalone via Docker

From the repo root:

```bash
docker-compose up
```

The web service runs migrations on startup (via `docker-entrypoint.sh`) and serves the app at **http://localhost:8000**.

To run migrations manually (e.g. in a one-off container):

```bash
docker-compose run web python project/manage.py migrate --noinput
```

## Running blueflow standalone (local, no Docker)

Ensure PostgreSQL is running, then:

```bash
uv pip install -e .
export DJANGO_SETTINGS_MODULE=project.settings.development
export DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
python project/manage.py migrate --noinput
python project/manage.py runserver
```
