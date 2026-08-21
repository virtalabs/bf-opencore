#!/usr/bin/env python

"""Django's command-line utility for the minimal blueflow project."""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings.development")
    try:
        from django.core.management import execute_from_command_line  # noqa: PLC0415
    except ImportError as exc:
        msg =  ("Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable?")
        raise ImportError(msg) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
