"""Asset tests.

Uses built-in pytest-django text fixtures from
http://pytest-django.readthedocs.io/en/latest/helpers.html
"""

import json

import pytest
from freezegun import freeze_time
from rest_framework import status
from rest_framework.test import APIClient

from blueflow import models


def test_get_empty_assets(auth_client: APIClient) -> None:
    """Test that asset list is empty unless we do something special."""
    assets = auth_client.get("/api/assets/")
    assert assets.data["count"] == 0


def test_create_asset(auth_client: APIClient) -> None:
    """Creating an empty asset makes it available via the API."""
    _ = models.Asset.objects.create()
    assets = auth_client.get("/api/assets/")
    assert assets.status_code == status.HTTP_200_OK
    assert assets.data["count"] == 1


def test_export_assets_json(auth_client: APIClient) -> None:
    """We can export assets to JSON."""
    _ = models.Asset.objects.create()
    response = auth_client.get("/api/assets/", HTTP_ACCEPT="application/json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    assert json.loads(response.content)


def test_api_create_asset(asset_edit_client: APIClient) -> None:
    """Create an asset with authorized client."""
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"hostname": "nospam", "manufacturer": "Acme"}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["hostname"] == "nospam"


def test_api_create_asset_maconly(asset_edit_client: APIClient) -> None:
    """Create an asset with authorized client."""
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"mac_address": "1", "manufacturer": "Acme"}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["mac_address"] == "00:00:00:00:00:01"


def test_api_create_asset_addinventory_maconly(asset_edit_client: APIClient) -> None:
    """Create an asset with MAC only, ip_address sent as null."""
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"mac_address": "1", "manufacturer": "Acme", "ip_address": None}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["mac_address"] == "00:00:00:00:00:01"
    assert asset["ip_address"] is None


def test_api_create_asset_empty_mac_rejected(asset_edit_client: APIClient) -> None:
    """Empty string MAC address is rejected with 400."""
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"mac_address": "", "ip_address": None}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_api_create_asset_empty_mac_rejected_twice(
    asset_edit_client: APIClient,
) -> None:
    """Empty string MAC address is rejected both times with 400."""
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"mac_address": "", "ip_address": None}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response = client.post(
        "/api/assets/",
        json.dumps({"mac_address": "", "ip_address": None}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert models.Asset.objects.count() == 0


@pytest.mark.xfail(reason="Authentication is not implemented yet")
def test_api_create_asset_unauthorized(auth_client: APIClient) -> None:
    """Can't create an asset with an unauthorized client."""
    client = auth_client
    response = client.post(
        "/api/assets/",
        json.dumps({"hostname": "nospam", "manufacturer": "Acme"}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 0
    assert len(assets.data["results"]) == 0


def test_api_create_get_asset(
    auth_client: APIClient, asset_edit_client: APIClient
) -> None:
    """Create an asset, read with less-authorized client."""
    response = asset_edit_client.post(
        "/api/assets/",
        json.dumps({"hostname": "nospam", "manufacturer": "Acme"}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assets = auth_client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["hostname"] == "nospam"


def test_api_create_patch_asset(
    auth_client: APIClient, asset_edit_client: APIClient
) -> None:
    """Create an asset, then patch."""
    response = asset_edit_client.post(
        "/api/assets/",
        json.dumps({"hostname": "nospam", "manufacturer": "Acme"}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["hostname"] == "nospam"
    asset_id = response.data["id"]
    response = asset_edit_client.patch(
        f"/api/assets/{asset_id}/",
        json.dumps({"hostname": "spam"}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["hostname"] == "spam"
    assets = auth_client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["hostname"] == "spam"


@pytest.mark.xfail(
    raises=AssertionError,
    reason="Not sure why, but we *are* allowed to patch.  "
    "Maybe there's a mix-up re: which user is which.",
)
def test_api_create_unauth_patch_asset(
    auth_client: APIClient, asset_edit_client: APIClient
) -> None:
    """Create an asset, patch with less-authorized client...

    ... except it fails.  See test_authentication.py::test_perm_auth_clients
    for an indication of why.

    NOTE: This really isn't a problem! See test below
      (test_unauth_patch_asset) where a client with insufficient
      authorization is unable to PATCH an asset.
    """
    response = asset_edit_client.post(
        "/api/assets/",
        json.dumps({"hostname": "nospam"}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["hostname"] == "nospam"
    asset_id = response.data["id"]
    response = auth_client.patch(
        f"/api/assets/{asset_id}/",
        json.dumps({"hostname": "spam"}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN  # <- this fails...
    assets = auth_client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["hostname"] == "nospam"


@pytest.mark.xfail(reason="Authentication is not currently implemented")
def test_unauth_patch_asset(auth_client: APIClient) -> None:
    """Create an asset, patch with less-authorized client.

    (auth_client is 'authenticated', not 'authorized')
    """
    _ = models.Asset.objects.create()
    response = auth_client.get("/api/assets/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["count"] == 1
    asset = response.json()["results"][0]
    assert asset["hostname"] is None
    response = auth_client.patch(
        "/api/assets/{}/".format(asset["id"]),
        json.dumps({"hostname": "spam"}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    response = auth_client.get("/api/assets/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["count"] == 1
    asset = response.json()["results"][0]
    assert asset["hostname"] is None  # Still None


def test_create_many_assets(auth_client: APIClient) -> None:
    """Creating multiple assets makes them available via the API."""
    asset_names = ["foo", "bar", "baz", "xyzzy", "spam", "ham", "eggs"]
    for name in asset_names:
        _ = models.Asset.objects.create(name=name)
    assets = auth_client.get("/api/assets/")
    assert assets.data["count"] == len(asset_names)


def test_retrieve_one_asset(auth_client: APIClient) -> None:
    """Creating an asset makes it available via the API."""
    asset_names = ["foo", "bar", "baz", "xyzzy", "spam", "ham", "eggs"]
    for hostname in asset_names:
        _ = models.Asset.objects.create(hostname=hostname)
    assets = auth_client.get("/api/assets/?hostname__icontains=xyzzy")
    assert assets.data["count"] == 1
    assert len(assets.data["results"]) == 1


def test_one_asset_details(auth_client: APIClient) -> None:
    """Creating an asset makes its details available via the API."""
    asset_names = ["foo", "bar", "baz", "xyzzy", "spam", "ham", "eggs"]
    for hostname in asset_names:
        _ = models.Asset.objects.create(hostname=hostname)
    # Note alternative query syntax
    assets = auth_client.get("/api/assets/", {"hostname__icontains": "xyzzy"})
    asset = assets.data["results"].pop()
    assert asset["hostname"] == "xyzzy"


def test_patch_asset(asset_edit_client: APIClient) -> None:
    """Patching an asset field updates the asset in the database."""
    client = asset_edit_client
    spam_asset = models.Asset.objects.create(hostname="spam")
    # Verify that hostname is what we set it to
    assert spam_asset.hostname == "spam"
    # Send PATCH request
    _ = client.patch(
        f"/api/assets/{spam_asset.id}/",
        json.dumps({"hostname": "nospam"}),
        content_type="application/json",
    )
    # Query for the new version of spam_asset, verify that its
    # hostname has changed.
    spam_asset = models.Asset.objects.get(id=spam_asset.id)
    assert spam_asset.hostname == "nospam"


def test_set_name_null(asset_edit_client: APIClient) -> None:
    """PATCHing hostname to null clears it.

    Required by the nullable-for-uniqueness contract.

    See test_asset_hostname.test_db_allows_multiple_null_hostnames for why
    the model is nullable. The API must let callers clear a hostname back
    to NULL or the contract is one-way only.
    """
    client = asset_edit_client
    spam_asset = models.Asset.objects.create(hostname="spam")
    assert spam_asset.hostname == "spam"
    response = client.patch(
        f"/api/assets/{spam_asset.id}/",
        json.dumps({"hostname": None}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_200_OK
    spam_asset = models.Asset.objects.get(id=spam_asset.id)
    assert spam_asset.hostname is None


def test_field_histogram(auth_client: APIClient) -> None:
    """Field histogram works with one field."""
    models.Asset.objects.create(manufacturer="Bar")
    models.Asset.objects.create(manufacturer="Quux")
    models.Asset.objects.create(manufacturer="Foo")
    models.Asset.objects.create(manufacturer="Foo")
    models.Asset.objects.create(manufacturer="Bar")
    models.Asset.objects.create(manufacturer="Foo")

    response = auth_client.get("/api/assets/histogram/", {"field": "manufacturer"})

    qset = response.data

    expected_count = 3
    assert len(qset) == expected_count
    # Order matters: the histogram is explicitly ordered by highest-count first
    assert [x["manufacturer"] for x in qset] == ["Foo", "Bar", "Quux"]
    assert [x["count"] for x in qset] == [3, 2, 1]


def test_field_histogram_no_field(auth_client: APIClient) -> None:
    """Fail to specify field=<Asset field name>: HTTP 400."""
    response = auth_client.get("/api/assets/histogram/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_field_histogram_no_such_field(auth_client: APIClient) -> None:
    """Specify field=<nonsense>: HTTP 400."""
    response = auth_client.get("/api/assets/histogram/", {"field": "asdf"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_api_duplicate_ips(auth_client: APIClient) -> None:
    """Check for duplicate IP addresses in the asset population."""
    response = auth_client.get("/api/assets/duplicate_ips/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []

    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(manufacturer="Foo", ip_address=None)
    response = auth_client.get("/api/assets/duplicate_ips/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        ["1.2.3.4", 3],
        ["1.2.3.5", 2],
    ]


def test_api_duplicate_ips_one(auth_client: APIClient) -> None:
    """Check for duplicate IP addresses in the asset population."""
    response = auth_client.get("/api/assets/duplicate_ips/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []

    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(manufacturer="Foo", ip_address=None)
    response = auth_client.get("/api/assets/duplicate_ips/?ip_address=1.2.3.4")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        ["1.2.3.4", 3],
    ]


@pytest.mark.xfail(
    raises=AssertionError,
    reason="not allowed to spell out 'exact' in URL for some reason.",
)
def test_api_duplicate_ips_one_spell_exact(auth_client: APIClient) -> None:
    """Check for duplicate IP addresses in the asset population."""
    response = auth_client.get("/api/assets/duplicate_ips/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []

    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(manufacturer="Foo", ip_address=None)
    response = auth_client.get("/api/assets/duplicate_ips/?ip_address__exact=1.2.3.4")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        ["1.2.3.4", 3],
    ]


def test_api_duplicate_ips_one_prefix_robust(auth_client: APIClient) -> None:
    """Check for duplicate IP addresses in the asset population."""
    response = auth_client.get("/api/assets/duplicate_ips/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []

    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.45")
    models.Asset.objects.create(ip_address="1.2.3.45")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(manufacturer="Foo", ip_address=None)
    response = auth_client.get("/api/assets/duplicate_ips/?ip_address=1.2.3.4")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        ["1.2.3.4", 3],
    ]


def test_fetch_by_os(auth_client: APIClient) -> None:
    """Assets can be fetched by OS field."""
    a1 = models.Asset.objects.create(os="Windows XP")
    a2 = models.Asset.objects.create(os="WinXP")
    a3 = models.Asset.objects.create(os="XP")

    response = auth_client.get("/api/assets/?os__iexact=XP")
    assert response.status_code == status.HTTP_200_OK
    js = response.json()
    assert js["count"] == 1
    assert js["results"][0]["id"] == a3.id

    response = auth_client.get("/api/assets/?os__icontains=XP")
    assert response.status_code == status.HTTP_200_OK
    js = response.json()
    expected_count = 3
    assert js["count"] == expected_count
    ids = {x["id"] for x in js["results"]}
    assert ids == {a1.id, a2.id, a3.id}

    response = auth_client.get("/api/assets/?os__istartswith=win")
    assert response.status_code == status.HTTP_200_OK
    js = response.json()
    expected_count_2 = 2
    assert js["count"] == expected_count_2
    ids = {x["id"] for x in js["results"]}
    assert ids == {a1.id, a2.id}


def test_api_create_asset_mac_autofill_nic(asset_edit_client: APIClient) -> None:
    """Create an asset with NIC vendor."""
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"mac_address": "34:36:3b:c4:7d:ec", "manufacturer": "Acme"}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["mac_address"] == "34:36:3b:c4:7d:ec"
    assert asset["oui_manufacturer"] == "Apple, Inc."


def test_api_create_asset_mac_reject_nic(asset_edit_client: APIClient) -> None:
    """Provided NIC vendor will be silently ignored."""
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps(
            {
                "mac_address": "34:36:3b:c4:7d:ec",
                "manufacturer": "Acme",
                "oui_manufacturer": "Appletown USA",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["mac_address"] == "34:36:3b:c4:7d:ec"
    assert asset["oui_manufacturer"] == "Apple, Inc."


def test_upsert_create(asset_edit_client: APIClient) -> None:
    """Create a new asset via upsert endpoint."""
    macaddr = "00:03:b1:b5:b6:48"
    response = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": macaddr,
                "manufacturer": "Acme",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["mac_address"] == macaddr
    assert response.data["oui_manufacturer"] is not None
    assert models.Asset.objects.count() == 1
    asset = models.Asset.objects.get()
    assert asset.mac_address == macaddr


def test_external_key_non_connector(db) -> None:
    """Test that external_keys JSON field accepts arbitrary key-value pairs."""
    foobar = models.Asset.objects.create(name="Foobar")
    foobar.external_keys = {"ECN": "12345"}
    foobar.save()
    assert foobar.external_keys["ECN"] == "12345"


def test_upsert_update(asset_edit_client: APIClient) -> None:
    """Update an existing asset via upsert endpoint."""
    # Create existing asset in database
    models.Asset.objects.create(mac_address="11:22:33:44:55:66")
    response = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": "11:22:33:44:55:66",
                "manufacturer": "Acme",
                "ip_address": "10.0.0.1",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["mac_address"] == "11:22:33:44:55:66"
    assert response.data["ip_address"] == "10.0.0.1"
    assert models.Asset.objects.count() == 1
    asset = models.Asset.objects.get()
    assert asset.mac_address == "11:22:33:44:55:66"
    assert str(asset.ip_address) == "10.0.0.1"


def test_upsert_no_mac_address(asset_edit_client: APIClient) -> None:
    """Upsert endpoint returns 400 when MAC address is missing."""
    response = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(
            {
                "ip_address": "10.0.0.1",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert models.Asset.objects.count() == 0


def test_upsert_no_mac_address_duplicate(asset_edit_client: APIClient) -> None:
    """PUT twice with the same IP but second lacks MAC — returns 400."""
    response = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": "11:22:33:44:55:66",
                "manufacturer": "Acme",
                "ip_address": "10.0.0.1",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    response = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(
            {
                "manufacturer": "Acme",
                "ip_address": "10.0.0.1",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert models.Asset.objects.count() == 1


def test_upsert_unknown_fields_ignored(asset_edit_client: APIClient) -> None:
    """PUT with unknown fields — serializer ignores them, asset is created."""
    response = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": "11:22:33:44:55:66",
                "manufacturer": "Acme",
                "ipv6_address": "0:0:0:0:0:ffff:a00:1",
                "connect_port_tcp": "2575",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert models.Asset.objects.count() == 1


def test_upsert_many_fields(asset_edit_client: APIClient) -> None:
    """PUT with fields typically provided by a scanner using canonical names."""
    response = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(
            {
                "ip_address": "10.0.0.155",
                "manufacturer": "Hospira",
                "services": [{"port": 2575, "protocol": "tcp"}],
                "mac_address": "00:03:b1:b5:b6:48",
                "name": "Hospira Plum A+",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert models.Asset.objects.count() == 1


def test_upsert_bad_key_ignored(asset_edit_client: APIClient) -> None:
    """PUT with unknown key — serializer ignores it, asset is created."""
    response = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": "11:22:33:44:55:66",
                "manufacturer": "Acme",
                "ipv12345_address": "10.0.0.1",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert models.Asset.objects.count() == 1


@pytest.mark.parametrize(
    ("date_range", "num_assets"),
    [
        ("today", 1),  # Today
        ("yesterday", 2),  # Yesterday
        # Past 7 days -- xfail due to django-filter bug
        # carltongibson/django-filter#873
        pytest.param("week", 4, marks=pytest.mark.xfail),
        ("month", 6),  # This month
        ("year", 7),  # This year
    ],
)
def test_asset_date_range(
    date_range: str, num_assets: int, auth_client: APIClient
) -> None:
    """Test that we can get assets from different date ranges.

    Using freezegun, creating assets today, yesterday, this week, etc.

    Note that the date_range takes a somewhat obscure integer argument:
     1 - Today
     2 - Past 7 days -- this is b0rken due to a timezone bug in django_filter
     3 - This month
     4 - This year
     5 - Yesterday

    2018-06-30 is a Saturday
    """
    with freeze_time("2018-06-30 12:00:00", tz_offset=0):
        models.Asset.objects.create(name="today")
    with freeze_time("2018-06-29 12:00:00", tz_offset=0):
        models.Asset.objects.create(name="yesterday_1")
        models.Asset.objects.create(name="yesterday_2")
    with freeze_time("2018-06-24 12:00:00", tz_offset=0):
        models.Asset.objects.create(name="this_week")
    with freeze_time("2018-06-23 10:00:00", tz_offset=0):
        models.Asset.objects.create(name="last_week")
    with freeze_time("2018-06-14 12:00:00", tz_offset=0):
        models.Asset.objects.create(name="this_month")
    with freeze_time("2018-05-14 12:00:00", tz_offset=0):
        models.Asset.objects.create(name="this_year")

    res = auth_client.get("/api/assets/")
    assert res.status_code == status.HTTP_200_OK
    total_assets = 7
    assert res.data["count"] == total_assets

    with freeze_time("2018-06-30 13:00:00", tz_offset=0):
        res = auth_client.get(f"/api/assets/?date_range={date_range}")
        assert res.data["count"] == num_assets


# ---------------------------------------------------------------------------
# Bulk PATCH tests
# ---------------------------------------------------------------------------


def test_bulk_update_updates_fields(asset_edit_client: APIClient) -> None:
    """PATCH /api/assets/bulk_update/ updates only the provided fields."""
    a1 = models.Asset.objects.create(hostname="device-a", os="Windows")
    a2 = models.Asset.objects.create(hostname="device-b", os="Linux")

    response = asset_edit_client.patch(
        "/api/assets/bulk_update/",
        json.dumps(
            [
                {"id": a1.id, "hostname": "device-a-updated"},
                {"id": a2.id, "os": "FreeBSD"},
            ]
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 2

    a1.refresh_from_db()
    a2.refresh_from_db()
    assert a1.hostname == "device-a-updated"
    assert a1.os == "Windows"  # untouched
    assert a2.os == "FreeBSD"
    assert a2.hostname == "device-b"  # untouched


def test_bulk_update_unknown_id_returns_404(asset_edit_client: APIClient) -> None:
    """PATCH /api/assets/bulk_update/ returns 404 if any id is not found."""
    a1 = models.Asset.objects.create(hostname="device-a")
    response = asset_edit_client.patch(
        "/api/assets/bulk_update/",
        json.dumps(
            [
                {"id": a1.id, "hostname": "updated"},
                {"id": 99999, "hostname": "ghost"},
            ]
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_bulk_update_missing_id_returns_400(asset_edit_client: APIClient) -> None:
    """PATCH /api/assets/bulk_update/ returns 400 if any item lacks an id."""
    response = asset_edit_client.patch(
        "/api/assets/bulk_update/",
        json.dumps([{"hostname": "no-id-here"}]),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_bulk_update_non_list_returns_400(asset_edit_client: APIClient) -> None:
    """PATCH /api/assets/bulk_update/ returns 400 if body is not a list."""
    response = asset_edit_client.patch(
        "/api/assets/bulk_update/",
        json.dumps({"id": 1, "hostname": "not-a-list"}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_bulk_update_duplicate_id_returns_400(asset_edit_client: APIClient) -> None:
    """PATCH /api/assets/bulk_update/ returns 400 if the same id appears twice."""
    asset = models.Asset.objects.create(hostname="device-a")
    response = asset_edit_client.patch(
        "/api/assets/bulk_update/",
        json.dumps(
            [
                {"id": asset.id, "hostname": "first"},
                {"id": asset.id, "hostname": "second"},
            ]
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_bulk_update_idempotent(asset_edit_client: APIClient) -> None:
    """Sending the same PATCH twice produces the same result."""
    asset = models.Asset.objects.create(hostname="original")
    payload = json.dumps([{"id": asset.id, "hostname": "updated"}])

    r1 = asset_edit_client.patch(
        "/api/assets/bulk_update/", payload, content_type="application/json"
    )
    r2 = asset_edit_client.patch(
        "/api/assets/bulk_update/", payload, content_type="application/json"
    )
    assert r1.status_code == status.HTTP_200_OK
    assert r2.status_code == status.HTTP_200_OK
    assert r1.data[0]["hostname"] == r2.data[0]["hostname"] == "updated"


# ---------------------------------------------------------------------------
# Section: PortProtocol / AssetPortProtocol model contract
# ---------------------------------------------------------------------------


def test_asset_add_service_idempotent(db: None) -> None:
    """``add_service`` returns True on first call, False on repeat; no dupes."""
    asset = models.Asset.objects.create(manufacturer="Acme")
    assert asset.add_service(80, "tcp") is True
    assert asset.add_service(80, "tcp") is False
    assert asset.port_protocols.count() == 1


def test_port_protocol_lookup_shared_across_assets(db: None) -> None:
    """Two assets with the same ``(port, protocol)`` reference one lookup row."""
    a1 = models.Asset.objects.create(manufacturer="Acme")
    a2 = models.Asset.objects.create(manufacturer="Acme")
    a1.add_service(80, "tcp")
    a2.add_service(80, "tcp")
    assert models.PortProtocol.objects.filter(port=80, protocol="tcp").count() == 1
    assert models.AssetPortProtocol.objects.count() == 2


def test_asset_delete_cascades_through_rows_keeps_lookup(
    db: None,
) -> None:
    """Deleting an asset removes its through-rows; the shared lookup survives."""
    a1 = models.Asset.objects.create(manufacturer="Acme")
    a2 = models.Asset.objects.create(manufacturer="Acme")
    a1.add_service(80, "tcp")
    a2.add_service(80, "tcp")
    assert models.AssetPortProtocol.objects.count() == 2

    a1.delete()
    assert models.AssetPortProtocol.objects.count() == 1
    assert models.PortProtocol.objects.filter(port=80, protocol="tcp").exists()
