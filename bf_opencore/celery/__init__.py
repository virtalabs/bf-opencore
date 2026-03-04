"""Celery instance for integrations.

One instance of Celery lives in this file.  All tasks in the integrations will
use this instance.

Based on Celery documentation:
http://docs.celeryproject.org/en/latest/getting-started/first-steps-with-celery.html

Quick start (from root blueflow/ directory)
$ celery -A bf_opencore.celery worker --loglevel=info &
...
[2017-06-30 16:36:12,453: INFO/MainProcess] celery@manzana.local ready.
$ python
>>> import bf_opencore.celery
>>> bf_opencore.celery.celery_app.tasks.ping.main.delay(hostname='localhost')
<AsyncResult: e8cfbb56-eca7-491d-a3a3-c15819cad8b8>
"""
import logging

import celery

logger = logging.getLogger(__name__)

# Create a Celery instance (sometimes called an app)
# http://docs.celeryproject.org/en/latest/getting-started/next-steps.html
celery_app = celery.Celery("bf_opencore")

# Use Django settings module for configuration
#
# Any configuration parameter that starts with CELERY_ will be read.  See
# notes in settings/defaults.py about logging configuration.  Search for
# "CELERY_WORKER_LOG_FORMAT".
#
# Celery docs
# http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html
celery_app.config_from_object(
    "django.conf:settings",
    namespace="CELERY",
    silent=False,
)

