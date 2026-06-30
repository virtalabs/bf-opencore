# =========================
#     Base
# =========================
FROM python:3.12-slim AS base

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
RUN uv sync --no-install-project --frozen

COPY blueflow/ ./blueflow/
COPY project/ ./project/
COPY tests/ ./tests/

# =========================
#     Development
# =========================
FROM base as develop

RUN uv sync --frozen --extra dev

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN useradd -m -u 1001 blueflow \
    && chown -R blueflow:blueflow /app \
    && chmod +x /app/docker-entrypoint.sh

USER blueflow

EXPOSE 8000
ENV DJANGO_SETTINGS_MODULE=project.settings.development
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["/bin/bash", "/app/docker-entrypoint.sh"]
CMD ["python", "project/manage.py", "runserver", "0.0.0.0:8000"]

# =========================
#     Production
# =========================
FROM base as prod

RUN uv sync --frozen --extra prod

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN useradd -m -u 1001 blueflow \
    && chown -R blueflow:blueflow /app \
    && chmod +x /app/docker-entrypoint.sh

USER blueflow

EXPOSE 8000
ENV DJANGO_SETTINGS_MODULE=project.settings.production
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["/bin/bash", "/app/docker-entrypoint.sh"]
CMD ["gunicorn", "project.wsgi:application", "--bind", "0.0.0.0:8000"]
