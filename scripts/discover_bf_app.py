#! /usr/bin/env python3
"""Discover BlueFlow app in Django settings."""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django.conf.global_settings")
from django.conf import global_settings

global_settings.INSTALLED_APPS = [*global_settings.INSTALLED_APPS, "blueflow.apps.BlueflowConfig"]

django.setup()

from django.apps import apps

config = apps.get_app_config("blueflow")
assert config.__class__.__name__ == "BlueflowConfig"
print("Blueflow app is discoverable:", config.name, config.verbose_name)  # noqa: T201
