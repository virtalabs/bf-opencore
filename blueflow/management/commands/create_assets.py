"""Load assets from a json file."""

import json
import pathlib
import typing
from collections import abc

from django.apps import apps
from django.core.management import base
from django.db import connection, transaction


class AssetJson(typing.TypedDict):
    pk: str
    fields: dict[str, str]


def _get_field(asset: AssetJson, key: str, parent: str = "fields") -> str:
    return asset[parent][key]


def make_assets(data: list[AssetJson]) -> abc.Generator[dict[str, str], None, None]:
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


def insert_assets(raw_assets: abc.Iterable[dict[str, str]]) -> None:
    """Bulk create assets.

    Asset is a child of the concrete model System. Thus django's
    bulk_create method wont work on Asset directly. The workaround below
    is to first bulk_create the parent using the IDs from the json file.
    Then drop into a manual bulk create SQL using `executemany` while
    providing the link to the parent column containing the ID.

    Alternatively it is also possible to forgo the manual insertion of IDs
    and let PostgreSQL handle the IDs itself. These can be obtained from the
    System.objects.bulk_create() response.
    """
    System = apps.get_model("blueflow", "System")
    Asset = apps.get_model("blueflow", "Asset")
    NetworkInterface = apps.get_model("blueflow", "NetworkInterface")
    with transaction.atomic():
        assets = list(raw_assets)
        _ = System.objects.bulk_create([System(id=a["id"]) for a in assets])
        _ = NetworkInterface.objects.bulk_create(
            [
                NetworkInterface(
                    system_id=a["id"],
                    ipv4=a["ip_address"],
                    mac_address=a["mac_address"],
                )
                for a in assets
            ]
        )
        asset_table = Asset._meta.db_table  # noqa: SLF001
        system_link = Asset._meta.parents[System].column  # noqa: SLF001
        with connection.cursor() as cursor:
            cursor.executemany(
                f"INSERT INTO {asset_table} "  # nosec B608 # noqa: S608
                f"({system_link}, name, hostname, "
                f"oui_manufacturer, "
                f"manufacturer, model, serial_number, "
                f"udi, tag_number, category, "
                f"owner, os, app_sw_version, "
                f"last_scanned, last_pinged, external_keys) "
                f"VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",  # noqa: E501
                [
                    (
                        a["id"],
                        a["name"],
                        a["hostname"],
                        a["oui_manufacturer"],
                        a["manufacturer"],
                        a["model"],
                        a["serial_number"],
                        a["udi"],
                        a["tag_number"],
                        a["category"],
                        a["owner"],
                        a["os"],
                        a["app_sw_version"],
                        a["last_scanned"],
                        a["last_pinged"],
                        a["external_keys"],
                    )
                    for a in assets
                ],
            )


class Command(base.BaseCommand):
    """Django manage.py sub command loads assets from a json file."""

    help = "Load assets from a json file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--filepath", type=str, required=True, help="The path to the json file"
        )

    def handle(self, *_, **options) -> None:
        file_path = options.get("filepath")
        if not file_path:
            msg = "Filepath can't be falsey"
            raise base.CommandError(msg)
        with pathlib.Path(file_path).open(encoding="utf-8") as file:
            data = json.load(file)
            assets = make_assets(data)
            insert_assets(assets)
        Asset = apps.get_model("blueflow", "Asset")
        self.stdout.write(self.style.SUCCESS(f"Loaded {Asset.objects.count()} assets"))
