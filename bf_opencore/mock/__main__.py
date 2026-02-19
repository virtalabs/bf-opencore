# Copyright (C) 2017 Virta Laboratories, Inc.  All rights reserved.

"""Top level interface for random asset generator."""
from collections import OrderedDict
import os
import logging
import random
import importlib
import celery
import click
from bf_opencore.celery import celery_app
from .mock import MockPopulation, MATH_PACKAGE_ERROR


logger = celery.utils.log.get_task_logger(__name__)


# Note: a subset of the command line inputs are available to the web GUI via
# this CONNECTOR_SPEC
CONNECTOR_SPEC = {
    "display_name": "Random Asset Generator",
    "description": "Generate random assets.",
    "hidden": True,
    "kwargs": OrderedDict([
        ("nassets", {
            "default": 100,
            "type": int,
            "help": "number of assets to create",
        }),
        ("manuf_pct", {
            "default": 100,
            "type": int,
            "help": '% assets to get "manufacturer" labels',
        }),
        ("model_pct", {
            "default": 100,
            "type": int,
            "help": '% assets w/ "manufacturer" labels to get "model" labels',
        }),
        ("os_pct", {
            "default": 80,
            "type": int,
            "help": '% assets to get "os" (operating system) labels',
        }),
        ("owner_pct", {
            "default": 80,
            "type": int,
            "help": '% assets to get "owner" labels',
        }),
        ("max_age", {
            "default": 60,
            "type": int,
            "help": "Maximum randomized age for assets",
        }),
    ]),
    'settings': OrderedDict(),
}
DEFAULTS = {k: v["default"] for k, v in CONNECTOR_SPEC["kwargs"].items()}

# This default is used internally
DEFAULT_POPFILE = os.path.join(os.path.dirname(__file__), "config.json")


@celery_app.task(bind=True)
def main(
        ctx,
        popfile=DEFAULT_POPFILE,
        nassets=DEFAULTS["nassets"],
        num_manufacturers=None,
        manuf_pct=DEFAULTS["manuf_pct"],
        model_pct=DEFAULTS["model_pct"],
        os_pct=DEFAULTS["os_pct"],
        owner_pct=DEFAULTS["owner_pct"],
        max_age=DEFAULTS["max_age"]
):
    """Create mock population of assets and add to database."""
    # This module started out powered by @click, where
    # too-many-arguments is not a style, it's a way of life.
    #
    # pylint: disable=too-many-arguments,too-many-locals

    # Protect your types
    nassets = int(nassets)
    manuf_pct = float(manuf_pct)
    model_pct = float(model_pct)
    os_pct = float(os_pct)
    owner_pct = float(owner_pct)
    max_age = int(max_age)

    pop = MockPopulation.from_file(popfile, num_manufacturers)
    created = pop.create_assets(nassets,
                                manuf_pct=manuf_pct, model_pct=model_pct,
                                max_age=max_age,
                                os_pct=os_pct, owner_pct=owner_pct)
    ctx.ct.print('Created {} assets.'.format(created))


@click.command(context_settings={"help_option_names": ['-h', '--help']})
@click.argument('popfile', type=click.Path(exists=True),
                default=DEFAULT_POPFILE)
@click.option('--nassets', type=int, default=DEFAULTS["nassets"])
@click.option('--num-manufacturers', type=int, default=None)
@click.option('--manuf-pct', type=int, default=DEFAULTS["manuf_pct"],
              help='% assets to get "manufacturer" labels')
@click.option('--model-pct', type=int, default=DEFAULTS["model_pct"],
              help='% assets w/ "manufacturer" labels to get "model" labels')
@click.option('--os-pct', type=int, default=DEFAULTS["os_pct"],
              help='% assets to get "os" labels')
@click.option('--owner-pct', type=int, default=DEFAULTS["owner_pct"],
              help='% assets to get "owner" labels')
@click.option('--max-age', type=int, default=DEFAULTS["max_age"],
              help='Maximum randomized age for assets')
@click.option('--repeatable/--no-repeatable', default=False,
              help='Hardcoded seed will ensure repeatability')
def cli(popfile, nassets, num_manufacturers, manuf_pct,
        model_pct, os_pct, owner_pct, max_age, repeatable):
    """Random asset generator."""
    # too-many-* is in part a function of @click.
    # pylint: disable=too-many-locals,too-many-arguments
    logger.setLevel(logging.DEBUG)

    if repeatable:
        try:
            np = importlib.import_module('numpy')
        except ImportError:
            logger.error(MATH_PACKAGE_ERROR)
            raise
        np.random.seed(0)
        random.seed(0)  # Hardcoded seed

    # pylint: disable=no-value-for-parameter
    main.apply(
        kwargs={
            'popfile': popfile,
            'nassets': nassets,
            'num_manufacturers': num_manufacturers,
            'manuf_pct': manuf_pct,
            'model_pct': model_pct,
            'os_pct': os_pct,
            'owner_pct': owner_pct,
            'max_age': max_age,
        }
    )


if __name__ == '__main__':
    cli()
