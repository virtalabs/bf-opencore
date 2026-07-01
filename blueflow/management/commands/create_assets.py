"""Load assets from a json file."""

import json
import pathlib
import typing
from collections import abc

from django.apps import apps
from django.core.management import base


def _get_field(asset: dict, key: str, parent: str = "fields") -> typing.Any:
    return asset.get(parent, {})[key]


def make_assets(data: list[dict]) -> abc.Generator[dict, None, None]:
    for asset in data:
        yield {
            "id": asset["pk"],
            "name": _get_field(asset, "name"),
            "hostname": _get_field(asset, "hostname"),
            "ip_address": _get_field(asset, "ip_address"),
            "mac_address": _get_field(asset, "mac_address"),
            "oui_manufacturer": _get_field(asset, "nic_vendor"),
            "manufacturer": _get_field(asset, "manufacturer"),
            "model": _get_field(asset, "model"),
            "serial_number": _get_field(asset, "serial_number"),
            "udi": _get_field(asset, "udi"),
            "tag_number": _get_field(asset, "tag_number"),
            "category": _get_field(asset, "category"),
            "owner": _get_field(asset, "owner"),
            "os": _get_field(asset, "os"),
            "app_sw_version": _get_field(asset, "app_sw_version"),
            "last_scanned": _get_field(asset, "last_scanned"),
            "last_pinged": _get_field(asset, "last_pinged"),
            "external_keys": _get_field(asset, "external_keys"),
        }


class Command(base.BaseCommand):
    """Django manage.py sub command loads assets from a json file."""

    help = "Load assets from a json file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--filepath", type=str, required=True, help="The path to the json file"
        )

    def handle(self, *_, **options) -> None:
        Asset = apps.get_model("blueflow", "Asset")
        file_path = options.get("filepath")
        with pathlib.Path(file_path).open(encoding="utf-8") as file:
            data = json.load(file)
            assets = make_assets(data)
            Asset.objects.bulk_create([Asset(**asset) for asset in assets])
        self.stdout.write(
            self.style.SUCCESS(f"Loaded {len(Asset.objects.all())} assets")
        )
