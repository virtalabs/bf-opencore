"""Load assets from a json file."""

import json
from collections.abc import Generator
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand


def make_assets(data: dict) -> Generator[dict, None, None]:
    for id, asset in data.items():
        yield {
            "id": id,
            "name": asset["name"],
            "hostname": asset["hostname"],
            "ip_address": asset["ip_address"],
            "mac_address": asset["mac_address"],
            "nic_vendor": asset["nic_vendor"],
            "manufacturer": asset["manufacturer"],
            "model": asset["model"],
            "serial_number": asset["serial_number"],
            "udi": asset["udi"],
            "tag_number": asset["tag_number"],
            "category": asset["category"],
            "owner": asset["owner"],
            "os": asset["os"],
            "app_sw_version": asset["app_sw_version"],
            "last_scanned": asset["last_scanned"],
            "last_pinged": asset["last_pinged"],
            "open_ports_tcp": asset["open_ports_tcp"],
            "external_keys": asset["external_keys"],
        }


class Command(BaseCommand):
    """Django manage.py sub command loads assets from a json file."""

    help = "Load assets from a json file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--filepath", type=str, required=True, help="The path to the json file"
        )

    def handle(self, *args, **options) -> None:
        Asset = apps.get_model("blueflow", "Asset")
        file_path = options.get("filepath")
        with Path(file_path).open(encoding="utf-8") as file:
            data = json.loads(file.read())
            assets = make_assets(data)
            Asset.objects.bulk_create([Asset(**asset) for asset in assets])
        self.stdout.write(
            self.style.SUCCESS(f"Loaded {len(Asset.objects.all())} assets")
        )
