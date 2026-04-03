"""Asset custom field history tests.

 - Canonical field: A field that's defined on the asset model
   Examples: hostname, ip_address, serial_number

 - Custom field: A field that's user-defined, and can be attached to an asset
   Examples: Location -- the system ships with a Location field; this
     is in fact a custom field and a user could rename or remove it.

For now, only accessing canonical fields, via the asset.  There's some
work going on, and some decisions being made, on whether custom fields
should be accssed via the asset or via its own API.
"""

from blueflow import models


def test_history_canonical_fields(asset_edit_client):
    """Check some rudimentary asset history."""
    a = models.Asset.objects.create()
    a.hostname = "spam"
    a.save()
    a.owner = "Hormel"
    a.save()
    a.hostname = "eggs"
    a.save()
    res = asset_edit_client.get(f"/api/assets/{a.id}/history/")
    # 4 history records: create, hostname=spam, owner=Hormel, hostname=eggs
    expected_owner_hist = ["Hormel", "Hormel", None, None]
    assert [h["owner"] for h in res.data["results"]] == expected_owner_hist
    expected_hostname_hist = ["eggs", "spam", "spam", None]
    assert [h["hostname"] for h in res.data["results"]] == expected_hostname_hist


def test_history_canonical_field_unchanged(asset_edit_client):
    """Unchanged field should show up as 'empty-ish'."""
    a = models.Asset.objects.create()
    res = asset_edit_client.get(f"/api/assets/{a.id}/history/?field=hostname")
    assert res.status_code == 200
    assert [h["hostname"] for h in res.data] == [None]


def test_history_canonical_one_field(asset_edit_client):
    """Field history should contain only the changes."""
    a = models.Asset.objects.create()
    a.hostname = "spam"
    a.save()
    a.owner = "Hormel"
    a.save()
    a.hostname = "eggs"
    a.save()
    res = asset_edit_client.get(f"/api/assets/{a.id}/history/?field=hostname")
    assert [h["hostname"] for h in res.data] == ["eggs", "spam", None]
