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

- **blueflow/** in this repo exists only for reference during the epic
  and will be removed when the epic is complete.
  The plan and deliverables use **bf_opencore** only.

## Install

```bash
uv pip install -e .
```

Or with optional dev dependencies:

```bash
uv pip install -e ".[dev]"
```

## Package

The installable app is the **bf_opencore** package. It can be added to any Django project via `INSTALLED_APPS` (e.g. `'bf_opencore'` or `'bf_opencore.apps.BfOpenCoreConfig'`).

## Running tests

Install with dev dependencies, then run pytest from the repo root. The test settings module is set automatically via `tests/conftest.py` (`DJANGO_SETTINGS_MODULE=project.settings.test`).

```bash
uv pip install -e ".[dev]"
pytest
```

To set the settings module explicitly:

```bash
DJANGO_SETTINGS_MODULE=project.settings.test pytest
```

## Running open-core standalone via Docker

From the repo root:

```bash
docker-compose up
```

The web service runs migrations on startup (via `docker-entrypoint.sh`) and serves the app at **http://localhost:8000**. To run migrations manually (e.g. in a one-off container):

```bash
docker-compose run web python project/manage.py migrate --noinput
```

## Running open-core standalone (local, no Docker)

Use the minimal project and development settings. Ensure PostgreSQL is running and set `DATABASE_URL` (or `DB_*` env vars). Then:

```bash
uv pip install -e .
export DJANGO_SETTINGS_MODULE=project.settings.development
export DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
python project/manage.py migrate --noinput
python project/manage.py runserver
```
