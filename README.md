# bf-opencore

BlueFlow open-core Django app. Installable package containing the `blueflow` Django application.

## Install

```bash
uv pip install -e .
```

Or with optional dev dependencies:

```bash
uv pip install -e ".[dev]"
```

## Package

The installable app is the `blueflow` package at the repo root. It can be added to any Django project via `INSTALLED_APPS` (e.g. `'blueflow'` or `'blueflow.apps.BlueflowConfig'`).
