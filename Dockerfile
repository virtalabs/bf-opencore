# Copyright (C) 2026 Virta Laboratories, Inc.  All rights reserved.
# Minimal Django project for standalone bf-opencore run.

FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY bf_opencore/ ./bf_opencore/
COPY project/ ./project/
COPY tests/ ./tests/

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv \
    && uv sync --frozen --no-dev

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN useradd -m -u 1001 blueflow \
    && chown -R blueflow:blueflow /app \
    && chmod +x /app/docker-entrypoint.sh

USER blueflow

EXPOSE 8000
ENV DJANGO_SETTINGS_MODULE=project.settings.development
ENTRYPOINT ["/bin/bash", "/app/docker-entrypoint.sh"]
CMD ["/app/.venv/bin/python", "project/manage.py", "runserver", "0.0.0.0:8000"]
