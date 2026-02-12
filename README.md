# bf-opencore

BlueFlow open-core Django app. Installable package containing the **bf_opencore** Django application.

## App identity

- **bf_opencore** is the installable Django app.
  - Add it to any Django project via `INSTALLED_APPS`
    (e.g. `'bf_opencore'` or `'bf_opencore.apps.BfOpenCoreConfig'`).
  - The main BlueFlow product (e.g. blueflow-saas) consumes bf-opencore
    as a dependency and uses it as a Django app.

- **Standalone run:** The minimal Django project in `project/` lets you
  run open-core by itself with no other repo:
  - `docker-compose up`, or
  - `python project/manage.py runserver`
  - Uses `INSTALLED_APPS = ['bf_opencore', ...]`.

## Install

```bash
uv pip install -e .
```

Or with optional dev dependencies:

```bash
uv pip install -e ".[dev]"
```

## Package

The installable app is the **bf_opencore** package. 
It can be added to any Django project via `INSTALLED_APPS` (e.g. `'bf_opencore'` or `'bf_opencore.apps.BfOpenCoreConfig'`).

## Running tests

All tests require PostgreSQL. Set `DATABASE_URL` to a Postgres URL (e.g. `postgresql://blueflow:blueflow@localhost:5432/blueflow`; with docker-compose use `postgresql://blueflow:blueflow@localhost:5432/blueflow` when the db service is exposed on localhost).

Run `uv sync --all-extras` (or `uv pip install -e ".[dev]"`) so pytest-django and dev deps are installed. Do not use a global or other `pytest` that might use a different interpreter or env. The test settings module is set automatically via `tests/conftest.py` (`DJANGO_SETTINGS_MODULE=project.settings.test`).

**Test layout**

- **`tests/`** (project-level): Smoke and functional tests for the minimal project (schema, URL wiring, migrations). Default `pytest` run collects only this directory (`testpaths = ["tests"]`).
- **`bf_opencore/tests/`** (app-level): Integration and functional tests for the bf_opencore app. Run explicitly when needed.

**Run project-level tests only**

```bash
export DATABASE_URL=postgresql://blueflow:blueflow@localhost:5432/blueflow
uv run pytest tests/
```

**Run project and app tests**

```bash
export DATABASE_URL=postgresql://blueflow:blueflow@localhost:5432/blueflow
uv run pytest tests/ bf_opencore/tests/
```

Or run only app tests:

```bash
export DATABASE_URL=postgresql://blueflow:blueflow@localhost:5432/blueflow
uv run pytest bf_opencore/tests/
```

## Running open-core standalone via Docker

From the repo root:

```bash
docker-compose up
```

The web service runs migrations on startup (via `docker-entrypoint.sh`) and serves the app at **http://localhost:8000**. 
To run migrations manually (e.g. in a one-off container):

```bash
docker-compose run web python project/manage.py migrate --noinput
```

## Running open-core standalone (local, no Docker)

Use the minimal project and development settings. 
Ensure PostgreSQL is running and set `DATABASE_URL` (or `DB_*` env vars). Then:

```bash
uv pip install -e .
export DJANGO_SETTINGS_MODULE=project.settings.development
export DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
python project/manage.py migrate --noinput
python project/manage.py runserver
```
