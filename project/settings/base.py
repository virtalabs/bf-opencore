"""Base Django settings (build-time config).

Do not set DATABASES, SECRET_KEY, DEBUG, ALLOWED_HOSTS here.
"""

import logging
import os

_log_format = os.environ.get("LOG_FORMAT", "").lower()

_raw_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
if _raw_log_level not in logging._nameToLevel:
    logging.warning("Invalid LOG_LEVEL %r — falling back to INFO", _raw_log_level)
    _raw_log_level = "INFO"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "fmt": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            **({"formatter": "json"} if _log_format == "json" else {}),
        },
    },
    "root": {
        "handlers": ["console"],
        "level": _raw_log_level,
    },
}

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
STATIC_ROOT = os.environ.get("STATIC_ROOT", "/app/staticfiles")
STATIC_URL = os.environ.get("STATIC_URL", "/static/")

INSTALLED_APPS = [
    "blueflow.apps.BlueflowConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.humanize",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_celery_beat",
    "django_filters",
    "netfields",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "simple_history",
    "waffle",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "waffle.middleware.WaffleMiddleware",
]

ROOT_URLCONF = "project.urls"
WSGI_APPLICATION = "project.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_SCHEMA_CLASS": "blueflow.spectacular.BlueflowSpectacularAutoSchema",
    "DEFAULT_PAGINATION_CLASS": "blueflow.pagination.HugeLimitOffsetPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
}
