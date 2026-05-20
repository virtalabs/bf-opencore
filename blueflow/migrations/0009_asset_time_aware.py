"""Migrate ``Asset`` from ``date_added``/``last_pinged`` to ``TimeStampedModel``.

The Viper webhook (``ViperWebhookResponseList.from_request``) used to filter
on ``last_pinged``, but TapirXL's ``PUT /api/assets/upsert/`` never sets that
field, so the first sync after a fresh boot returned an empty queryset (#158).

This migration:

1. Adds ``created`` / ``modified`` via django-extensions' ``TimeStampedModel``.
2. Backfills both from existing data so the webhook keeps returning the same
   assets it would have if ``last_pinged`` were correctly populated:
   ``created  = date_added``
   ``modified = COALESCE(last_pinged, date_added, NOW())``
3. Drops ``date_added`` (its semantic role is now ``created``).

``last_pinged`` is retained but its meaning is narrowed to "last observed on
the wire" — see ``Asset`` docstring.
"""

import django_extensions.db.fields
from django.db import migrations
from django.utils import timezone


def backfill_timestamps(apps, schema_editor):
    Asset = apps.get_model("blueflow", "Asset")
    HistoricalAsset = apps.get_model("blueflow", "HistoricalAsset")
    now = timezone.now()

    for asset in Asset.objects.all().iterator():
        Asset.objects.filter(pk=asset.pk).update(
            created=asset.date_added or now,
            modified=asset.last_pinged or asset.date_added or now,
        )

    for hist in HistoricalAsset.objects.all().iterator():
        HistoricalAsset.objects.filter(pk=hist.pk).update(
            created=hist.date_added or now,
            modified=hist.last_pinged or hist.date_added or now,
        )


def restore_date_added(apps, schema_editor):
    Asset = apps.get_model("blueflow", "Asset")
    HistoricalAsset = apps.get_model("blueflow", "HistoricalAsset")

    for asset in Asset.objects.all().iterator():
        Asset.objects.filter(pk=asset.pk).update(date_added=asset.created)

    for hist in HistoricalAsset.objects.all().iterator():
        HistoricalAsset.objects.filter(pk=hist.pk).update(date_added=hist.created)


class Migration(migrations.Migration):

    dependencies = [
        ("blueflow", "0008_remove_asset_risk_score_remove_asset_risk_score_cli_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="created",
            field=django_extensions.db.fields.CreationDateTimeField(
                auto_now_add=True,
                default=timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="asset",
            name="modified",
            field=django_extensions.db.fields.ModificationDateTimeField(
                auto_now=True,
                default=timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="historicalasset",
            name="created",
            field=django_extensions.db.fields.CreationDateTimeField(
                blank=True,
                editable=False,
                default=timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="historicalasset",
            name="modified",
            field=django_extensions.db.fields.ModificationDateTimeField(
                blank=True,
                editable=False,
                default=timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_timestamps, reverse_code=restore_date_added),
        migrations.RemoveField(model_name="asset", name="date_added"),
        migrations.RemoveField(model_name="historicalasset", name="date_added"),
    ]
