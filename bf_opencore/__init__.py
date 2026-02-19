
"""Connectors connect BlueFlow to the outside world.

Most connectors add assets to the database.

A typical connector can be called
 1. From the command line
 2. As a synchronous Python API
 3. As an asynchronous Python API using Celery and RabbitMQ

Example 1: CLI
    $ blueflow-connector-csv tests/data/csv-connector-input.csv

Example 2: Synchronous API
    $ python
    >>> import bf_opencore
    >>> bf_opencore.mock.main.apply(kwargs={'nassets': 100})

Example 3: Asynchronous API
    $ celery -A bf_opencore worker --loglevel=info &
    $ python
    >>> import bf_opencore
    >>> bf_opencore.mock.main.apply_async(kwargs={'nassets': 100})
"""

import os
import sys
import importlib

import django


################################################################
# First set up Django (if necessary)

def blueflow_django_setup():
    """Set DJANGO_SETTINGS_MODULE and PYTHONPATH, then call django.setup().

    Calling django.setup() is required for standalone Django usage.  setup()
    requires a settings module, which we'll specificy with the environment
    variable DJANGO_SETTINGS_MODULE.

    We need find the Django settings module which is inside our Django
    project in the outer app/ directory.  Add the absolute path to the Django
    project directory to the PYTHONPATH environment variable.
    """
    # django.setup() may only be called once.  This is not a problem for
    # standalone scripts.  However, if `import models` is called from a
    # Django view, for example, then setup() would be called twice.
    #
    # One effect of django.setup being run is that django gets the
    # attribute django.apps -- so testing for the existence of this is a
    # quick and dirty way to know whether we need to run the setup.
    #
    # From https://stackoverflow.com/a/39791949/3061818
    #
    # A better solution is something like
    # https://stackoverflow.com/a/40081252/3061818
    if hasattr(django, 'apps'):
        # django.setup() has already been called
        return
    blueflow_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    django_root = os.path.join(blueflow_root, "app")
    sys.path.append(django_root)

    # HACK: For some reason unknown to me (awdeorio 2018-09-20), connectors run
    # from the command line refuse to find 'app.settings'.  They work with
    # 'app.app.settings'.  Django's manage.py is the opposite.  This hack
    # prepends 'app.' to DJANGO_SETTINGS_MODULE.
    #
    # This bug is possibly related to the fact that Python the outer 'app
    # is a namespace, not a module.
    if os.path.basename(sys.argv[0]).startswith("blueflow-connector-"):
        if 'DJANGO_SETTINGS_MODULE' in os.environ:
            assert not os.environ['DJANGO_SETTINGS_MODULE']\
                        .startswith('app.app')
            os.environ['DJANGO_SETTINGS_MODULE'] = "app.{}".format(
                os.environ['DJANGO_SETTINGS_MODULE']
            )
        else:
            os.environ['DJANGO_SETTINGS_MODULE'] = "app.app.settings"

    django.setup()


blueflow_django_setup()


################################################################
# Then import/provide the connectors

class CData:
    """Hold Connector name and enabledness at install time."""

    # pylint: disable=too-few-public-methods

    def __init__(self, name, default_enabled=False):
        """Set connector data (default_enabled defaults to False)."""
        self.name = name
        self.default_enabled = default_enabled


# Instead of doing `from . import <connector-module>` we use importlib.
# This way we provide a list of "valid" connectors to our clients.
CONNECTORS = [
    CData(name="csv", default_enabled=True),
    CData(name="ping", default_enabled=True),
    CData(name="portscan", default_enabled=True),
    CData(name="fingerprint"),
]

for c in CONNECTORS:
    importlib.import_module('bf_opencore.{c.name}'.format(c=c))
