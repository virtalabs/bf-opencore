from django.db import migrations

CONSTRAINT_SQL = """
ALTER TABLE blueflow_asset
ADD CONSTRAINT asset_open_ports_tcp_valid_range CHECK (
    array_length(open_ports_tcp, 1) IS NULL
    OR (SELECT bool_and(p >= 1 AND p <= 65535)
        FROM unnest(open_ports_tcp) AS p)
);
"""

DROP_CONSTRAINT_SQL = """
ALTER TABLE blueflow_asset
DROP CONSTRAINT IF EXISTS asset_open_ports_tcp_valid_range;
"""


def _remove_invalid_tcp_ports(apps, _schema_editor):
    _tcp_port_max = 65535
    Asset = apps.get_model("blueflow", "Asset")
    for asset in Asset.objects.exclude(open_ports_tcp=[]):
        cleaned = [p for p in asset.open_ports_tcp if 1 <= p <= _tcp_port_max]
        if cleaned != asset.open_ports_tcp:
            asset.open_ports_tcp = cleaned
            asset.save()


class Migration(migrations.Migration):

    dependencies = [
        ("blueflow", "0005_asset_hostname_unique"),
    ]

    operations = [
        migrations.RunPython(
            _remove_invalid_tcp_ports,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunSQL(CONSTRAINT_SQL, DROP_CONSTRAINT_SQL),
    ]
