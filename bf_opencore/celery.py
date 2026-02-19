# Copyright (C) 2017 Virta Laboratories, Inc.  All rights reserved.

"""
Celery instance for connectors.

One instance of Celery lives in this file.  All tasks in the connectors will
use this instance.

Based on Celery documentation:
http://docs.celeryproject.org/en/latest/getting-started/first-steps-with-celery.html

Quick start (from root blueflow/ directory)
$ celery -A connectors worker --loglevel=info &
...
[2017-06-30 16:36:12,453: INFO/MainProcess] celery@manzana.local ready.
$ python
>>> import connectors
>>> connectors.tasks.load_mock.delay()
<AsyncResult: e8cfbb56-eca7-491d-a3a3-c15819cad8b8>
"""
import celery

# Signals are used to hook into the Celery Task lifecycle.  We use them to
# update our database with the status of a task.  Edit the actions caused by
# these signals in ./signals.py
#
# The purpose of this import is to register the callbacks.
from bf_opencore import signals

# Create a Celery instance (sometimes called an app)
# Based on Celery documentation found at
#
# Celery docs
# http://docs.celeryproject.org/en/latest/getting-started/next-steps.html
# http://docs.celeryproject.org/en/latest/reference/celery.html#celery.Celery.config_from_object
# http://docs.celeryproject.org/en/latest/userguide/configuration.html
celery_app = celery.Celery('bf_opencore')

# Use Django settings module for configuration
#
# Any configuration parameter that starts with CELERY_ will be read.  See
# notes in settings/defaults.py about logging configuration.  Search for
# "CELERY_WORKER_LOG_FORMAT".
#
# Celery docs
# http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html
celery_app.config_from_object(
    'django.conf:settings',
    namespace='CELERY',
    silent=False,
)
