from django.db import migrations, models


def _empty_hostnames_to_null(apps, schema_editor):
    """Convert any existing hostname='' rows to NULL.

    Required before the new CheckConstraint can apply: it rejects empty
    strings, and the new unique index treats '' as a real value (would
    collide if multiple rows share it).
    """
    asset = apps.get_model("blueflow", "Asset")
    asset.objects.filter(hostname="").update(hostname=None)


class Migration(migrations.Migration):

    dependencies = [
        ("blueflow", "0004_remove_pulse_feed_item"),
    ]

    operations = [
        migrations.RunPython(
            _empty_hostnames_to_null,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="asset",
            name="hostname",
            field=models.TextField(null=True, unique=True),
        ),
        migrations.AlterField(
            model_name="historicalasset",
            name="hostname",
            field=models.TextField(db_index=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="asset",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("hostname__isnull", True),
                    models.Q(("hostname", ""), _negated=True),
                    _connector="OR",
                ),
                name="asset_hostname_not_empty_when_set",
            ),
        ),
    ]
