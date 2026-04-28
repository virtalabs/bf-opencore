"""Ingest Zeek logs as Asset records.

Reads Zeek JSON logs from a directory, aggregates per-device payloads, and
upserts Assets keyed on MAC address. Mirrors the merge semantics of
``PUT /api/assets/upsert/`` (see ``blueflow/views/asset.py``) so an asset
seen by both Zeek and the HTTP upsert path stays a single row.

Usage:
    python manage.py zeek_ingest --logdir /path/to/zeek/logs/
"""

from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from blueflow.views.asset import AssetUpsertSerializer
from blueflow.zeek.sidecar import payloads_from_logdir


class Command(BaseCommand):
    """Upsert Assets from a directory of Zeek JSON logs."""

    help = "Upsert Assets from a directory of Zeek JSON logs (hl7.log + conn.log)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--logdir",
            type=str,
            required=True,
            help="Directory containing Zeek JSON logs (hl7.log, conn.log).",
        )

    def handle(self, *args, **options) -> None:  # noqa: ARG002
        logdir = Path(options["logdir"])
        if not logdir.is_dir():
            msg = f"Not a directory: {logdir}"
            raise CommandError(msg)

        payloads = payloads_from_logdir(logdir)
        if not payloads:
            self.stdout.write("No HL7 entries found; nothing to ingest.")
            return

        Asset = apps.get_model("blueflow", "Asset")
        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for payload in payloads:
                serializer = AssetUpsertSerializer(data=payload)
                serializer.is_valid(raise_exception=True)
                validated = dict(serializer.validated_data)
                mac = validated.pop("mac_address")
                new_ports = validated.pop("open_ports_tcp", [])

                asset = Asset.objects.filter(mac_address=mac).first()
                if asset is None:
                    Asset.objects.create(
                        mac_address=mac,
                        open_ports_tcp=new_ports,
                        **validated,
                    )
                    created_count += 1
                else:
                    if new_ports:
                        merged = sorted(set(asset.open_ports_tcp) | set(new_ports))
                        if merged != asset.open_ports_tcp:
                            validated["open_ports_tcp"] = merged
                    for k, v in validated.items():
                        setattr(asset, k, v)
                    asset.save()
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Zeek ingest: {created_count} created, {updated_count} updated."
            )
        )
