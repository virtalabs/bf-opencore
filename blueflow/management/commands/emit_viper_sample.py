"""Emit a sample Viper integrationUpload page payload from real BlueFlow assets."""

import json
import sys
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from blueflow.models import Asset
from blueflow.models.viper import ViperAsset, ViperWebhookResponse

# Same TapirXL-derived records as test_tapirxl_viper_regression GE fixtures.
# ``model`` is set explicitly — ViperAsset requires it; upsert ``product`` does not
# map to ``model`` today.
_GEHEALTHCARE_ASSETS: list[dict] = [
    {
        "hostname": "BRIGHTSPEED01",
        "ip_address": "10.40.2.20",
        "mac_address": "00:10:18:AA:BB:01",
        "manufacturer": "gehealthcare",
        "model": "brightspeed_elite_select",
        "app_sw_version": "11.2.0",
        "category": "CT",
    },
    {
        "hostname": "PACS-CENTRICITY-001",
        "ip_address": "10.40.2.10",
        "mac_address": "00:1A:2B:3C:51:10",
        "manufacturer": "gehealthcare",
        "model": "centricity_pacs_iw",
        "category": "pacs",
    },
]


class Command(BaseCommand):
    """Write a Viper webhook page body JSON sample to stdout or --output."""

    help = (
        "Emit a Viper integrationUpload page payload from seeded GE Healthcare assets"
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--output",
            type=str,
            default="-",
            help="Output file path (default: stdout)",
        )

    def handle(self, *_args, **options) -> None:
        macs = [fields["mac_address"] for fields in _GEHEALTHCARE_ASSETS]
        for fields in _GEHEALTHCARE_ASSETS:
            mac = fields["mac_address"]
            defaults = {k: v for k, v in fields.items() if k != "mac_address"}
            Asset.objects.update_or_create(mac_address=mac, defaults=defaults)
            asset = Asset.objects.get(mac_address=mac)
            asset.update_usage(timezone.now())

        assets = Asset.objects.filter(mac_address__in=macs).prefetch_related("usage")
        if assets.count() != len(_GEHEALTHCARE_ASSETS):
            self.stderr.write(
                self.style.ERROR(
                    f"Expected {len(_GEHEALTHCARE_ASSETS)} seeded assets, "
                    f"found {assets.count()}"
                )
            )
            sys.exit(1)

        items = [ViperAsset(asset) for asset in assets]
        page = ViperWebhookResponse(
            items=items,
            page=1,
            page_size=100,
            total_count=len(items),
            total_pages=1,
            since="1800-01-01T00:00:00Z",
        )
        payload = json.dumps(page.to_dict(), indent=2, sort_keys=True)
        output = options["output"]
        if output == "-":
            self.stdout.write(payload)
        else:
            Path(output).write_text(payload + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Wrote Viper sample to {output}"))
