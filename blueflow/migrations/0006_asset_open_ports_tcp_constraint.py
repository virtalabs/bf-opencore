from django.db import migrations

# PostgreSQL forbids subqueries inside CHECK expressions. Delegate validation to an
# IMMUTABLE SQL function so migration applies cleanly on PostgreSQL.
_CREATE_FN_SQL = """
CREATE FUNCTION blueflow_asset_open_ports_tcp_valid(p_ports integer[])
RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT COALESCE(
        NOT EXISTS (
            SELECT 1
            FROM unnest(COALESCE(p_ports, '{}'::integer[])) AS u(p)
            WHERE u.p < 1 OR u.p > 65535
        ),
        TRUE
    );
$$;
"""

_DROP_FN_SQL = """
DROP FUNCTION IF EXISTS blueflow_asset_open_ports_tcp_valid(integer[]);
"""

_ADD_CONSTRAINT_SQL = """
ALTER TABLE blueflow_asset
ADD CONSTRAINT asset_open_ports_tcp_valid_range
CHECK (blueflow_asset_open_ports_tcp_valid(open_ports_tcp));
"""

_DROP_CONSTRAINT_SQL = """
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
        migrations.RunSQL(
            sql=[
                _CREATE_FN_SQL,
                _ADD_CONSTRAINT_SQL,
            ],
            reverse_sql=[
                _DROP_CONSTRAINT_SQL,
                _DROP_FN_SQL,
            ],
        ),
    ]
