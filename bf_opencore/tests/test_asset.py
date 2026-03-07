"""Asset tests.

Uses built-in pytest-django text fixtures from
http://pytest-django.readthedocs.io/en/latest/helpers.html
"""

import json

import django
import pytest

from freezegun import freeze_time

from bf_opencore import models


@pytest.mark.django_db
def test_get_empty_assets(auth_client):
    """Test that asset list is empty unless we do something special."""
    assets = auth_client.get("/api/assets/")
    assert assets.data["count"] == 0


@pytest.mark.django_db
def test_create_asset(auth_client):
    """Creating an empty asset makes it available via the API."""
    _ = models.Asset.objects.create()
    assets = auth_client.get("/api/assets/")
    assert assets.status_code == 200
    assert assets.data["count"] == 1


@pytest.mark.django_db
def test_get_asset_csv(auth_client):
    """We can specify CSV format."""
    _ = models.Asset.objects.create()
    # import pdb ; pdb.set_trace()
    response = auth_client.get("/api/assets/", HTTP_ACCEPT="text/csv")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert len(response.content.splitlines()) == 2  # header row + 1 asset


@pytest.mark.django_db
def test_get_asset_csv_specify_fields(auth_client):
    """With CSV format we generally would specify which headers we want."""
    _ = models.Asset.objects.create(name="spam", ip_address="10.0.0.1")
    # import pdb ; pdb.set_trace()
    response = auth_client.get(
        "/api/assets/?fields=name,ip_address,model", HTTP_ACCEPT="text/csv"
    )
    header, *assets = response.content.splitlines()
    header = header.decode("utf-8").split(",")
    assert len(assets) == 1
    asset = assets.pop().decode("utf-8").split(",")
    assert header == ["name", "ip_address", "model"]
    assert asset == ["spam", "10.0.0.1", ""]


@pytest.mark.django_db
def test_export_assets_json(auth_client):
    """We can export assets to JSON."""
    _ = models.Asset.objects.create()
    # import pdb ; pdb.set_trace()
    response = auth_client.get("/api/assets/", HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert json.loads(response.content)


@pytest.mark.django_db
def test_api_create_asset(asset_edit_client):
    """Create an asset with authorized client."""
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"hostname": "nospam"}),
        content_type="application/json",
    )
    assert response.status_code == 201  # 201 = Created
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["hostname"] == "nospam"


@pytest.mark.django_db
def test_api_create_asset_maconly(asset_edit_client):
    """Create an asset with authorized client."""
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"mac_address": "1"}),
        content_type="application/json",
    )
    assert response.status_code == 201  # 201 = Created
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["mac_address"] == "00:00:00:00:00:01"


@pytest.mark.django_db
def test_api_create_asset_addinventory_maconly(asset_edit_client):
    """Create an asset, replicating 'add inventory.

    This replicates 'add inventory' where the IP address is empty -- it
    gets sent as '' rather than as 'null'.
    """
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"mac_address": "1", "ip_address": ""}),
        content_type="application/json",
    )
    assert response.status_code == 201  # 201 = Created
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["mac_address"] == "00:00:00:00:00:01"
    assert asset["ip_address"] is None


@pytest.mark.django_db
def test_api_create_asset_addinventory_empty_mac(asset_edit_client):
    """Create an asset, replicating 'add inventory.

    This replicates 'add inventory' where the MAC address is empty -- it
    gets sent as '' rather than as 'null'.
    """
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"mac_address": "", "ip_address": ""}),
        content_type="application/json",
    )
    assert response.status_code == 201  # 201 = Created
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["mac_address"] is None
    assert asset["ip_address"] is None


@pytest.mark.django_db
def test_api_create_asset_addinventory_empty_mac_times_two(asset_edit_client):
    """Create an asset, replicating 'add inventory'.

    This replicates 'add inventory' where the MAC address is empty, and
    where there was already an asset with an empty MAC address (Github
    issue https://github.com/virtalabs/blueflow/issues/2266)
    """
    client = asset_edit_client
    # Create the first asset
    response = client.post(
        "/api/assets/",
        json.dumps({"mac_address": "", "ip_address": ""}),
        content_type="application/json",
    )
    assert response.status_code == 201  # 201 = Created
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 1
    # Create the second asset
    response = client.post(
        "/api/assets/",
        json.dumps({"mac_address": "", "ip_address": ""}),
        content_type="application/json",
    )
    assert response.status_code == 201  # 201 = Created
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 2


@pytest.mark.django_db
def test_api_create_asset_unauthorized(auth_client):
    """Can't create an asset with an unauthorized client."""
    client = auth_client
    response = client.post(
        "/api/assets/",
        json.dumps({"hostname": "nospam"}),
        content_type="application/json",
    )
    assert response.status_code == 403  # 403 = Not permitted
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 0
    assert len(assets.data["results"]) == 0


@pytest.mark.django_db
def test_api_create_get_asset(auth_client, asset_edit_client):
    """Create an asset, read with less-authorized client."""
    response = asset_edit_client.post(
        "/api/assets/",
        json.dumps({"hostname": "nospam"}),
        content_type="application/json",
    )
    assert response.status_code == 201  # 201 = Created
    assets = auth_client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["hostname"] == "nospam"


@pytest.mark.django_db
def test_api_create_asset_open_ports(asset_edit_client):
    """Create an asset with authorized client.

    As if from http://localhost:8000/inventory/add/.
    """
    client = asset_edit_client
    post_data = {"open_ports_tcp": "8000 80,443, 80"}
    response = client.post(
        "/api/assets/", json.dumps(post_data), content_type="application/json"
    )
    assert response.status_code == 201  # 201 = Created
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["open_ports_tcp"] == [80, 443, 8000]


@pytest.mark.django_db
def test_api_create_patch_asset(auth_client, asset_edit_client):
    """Create an asset, then patch."""
    response = asset_edit_client.post(
        "/api/assets/",
        json.dumps({"hostname": "nospam"}),
        content_type="application/json",
    )
    assert response.status_code == 201  # 201 = Created
    assert response.data["hostname"] == "nospam"
    asset_id = response.data["id"]
    response = asset_edit_client.patch(
        f"/api/assets/{asset_id}/",
        json.dumps({"hostname": "spam"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.data["hostname"] == "spam"
    assets = auth_client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["hostname"] == "spam"


@pytest.mark.django_db
def test_api_create_asset_displayname(asset_edit_client):
    """Create an asset with a display_name."""
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"display_name": "foobar"}),
        content_type="application/json",
    )
    assert response.status_code == 201  # 201 = Created
    assert response.data["name"] == "foobar"
    assert response.data["display_name"] == "foobar"


@pytest.mark.django_db
def test_api_create_asset_displayname_name(asset_edit_client):
    """Create an asset with a display_name *and* a name.

    The display_name provided will be favoured.
    This is possibly confusing... but it is how it works.
    One could argue that this should produce a 500 or a 4xx (and that
    creation should fail), but I don't know how to do it (and it's
    really a minor issue IMHO.)
    """
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"name": "foobaz", "display_name": "foobar"}),
        content_type="application/json",
    )
    assert response.status_code == 201  # 201 = Created
    assert response.data["name"] == "foobar"  # NOTE: display_name is favored
    assert response.data["display_name"] == "foobar"


@pytest.mark.django_db
def test_api_create_asset_displayname_name_2(asset_edit_client):
    """Create an asset with a display_name *and* a name.

    Like the test above, but order of name/display name is reversed.
    display_name is still favoured.
    """
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"display_name": "foobar", "name": "foobaz"}),
        content_type="application/json",
    )
    assert response.status_code == 201  # 201 = Created
    assert response.data["name"] == "foobar"  # NOTE: display_name is favored
    assert response.data["display_name"] == "foobar"


@pytest.mark.django_db
def test_api_update_asset_displayname(asset_edit_client):
    """Create an asset, update display_name later."""
    client = asset_edit_client
    response = client.post(
        "/api/assets/", json.dumps({"name": "nospam"}), content_type="application/json"
    )
    assert response.data["name"] == "nospam"
    assert response.data["display_name"] == "nospam"
    asset_id = response.data["id"]
    response = client.patch(
        f"/api/assets/{asset_id}/",
        json.dumps({"display_name": "spam"}),
        content_type="application/json",
    )
    assert response.status_code == 200  # 200 = Updated
    assert response.data["name"] == "spam"
    assert response.data["display_name"] == "spam"


@pytest.mark.django_db
@pytest.mark.xfail(
    raises=AssertionError,
    reason="Not sure why, but we *are* allowed to patch.  "
    "Maybe there's a mix-up re: which user is which.",
)
def test_api_create_unauth_patch_asset(auth_client, asset_edit_client):
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
    assert response.status_code == 201  # 201 = Created
    assert response.data["hostname"] == "nospam"
    asset_id = response.data["id"]
    response = auth_client.patch(
        f"/api/assets/{asset_id}/",
        json.dumps({"hostname": "spam"}),
        content_type="application/json",
    )
    assert response.status_code == 403  # <- this fails...
    assets = auth_client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["hostname"] == "nospam"


@pytest.mark.django_db
def test_unauth_patch_asset(auth_client):
    """Create an asset, patch with less-authorized client.

    (auth_client is 'authenticated', not 'authorized')
    """
    _ = models.Asset.objects.create()
    response = auth_client.get("/api/assets/")
    assert response.status_code == 200  # 200 = Created
    assert response.json()["count"] == 1
    asset = response.json()["results"][0]
    assert asset["hostname"] is None
    response = auth_client.patch(
        "/api/assets/{}/".format(asset["id"]),
        json.dumps({"hostname": "spam"}),
        content_type="application/json",
    )
    assert response.status_code == 403
    response = auth_client.get("/api/assets/")
    assert response.status_code == 200  # 200 = Created
    assert response.json()["count"] == 1
    asset = response.json()["results"][0]
    assert asset["hostname"] is None  # Still None


@pytest.mark.django_db
def test_create_many_assets(auth_client):
    """Creating multiple assets makes them available via the API."""
    asset_names = ["foo", "bar", "baz", "xyzzy", "spam", "ham", "eggs"]
    for name in asset_names:
        _ = models.Asset.objects.create(name=name)
    assets = auth_client.get("/api/assets/")
    assert assets.data["count"] == len(asset_names)


@pytest.mark.django_db
def test_retrieve_one_asset(auth_client):
    """Creating an asset makes it available via the API."""
    asset_names = ["foo", "bar", "baz", "xyzzy", "spam", "ham", "eggs"]
    for hostname in asset_names:
        _ = models.Asset.objects.create(hostname=hostname)
    assets = auth_client.get("/api/assets/?hostname__icontains=xyzzy")
    assert assets.data["count"] == 1
    assert len(assets.data["results"]) == 1


@pytest.mark.django_db
def test_one_asset_details(auth_client):
    """Creating an asset makes its details available via the API."""
    asset_names = ["foo", "bar", "baz", "xyzzy", "spam", "ham", "eggs"]
    for hostname in asset_names:
        _ = models.Asset.objects.create(hostname=hostname)
    # Note alternative query syntax
    assets = auth_client.get("/api/assets/", {"hostname__icontains": "xyzzy"})
    asset = assets.data["results"].pop()
    assert asset["hostname"] == "xyzzy"


@pytest.mark.django_db
def test_patch_asset(asset_edit_client):
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


@pytest.mark.django_db
def test_patch_asset_open_ports_tcp_string(asset_edit_client):
    """Patching ports with a string of integers.

    We try to be helpful, and sort the resulting list & make it unique.
    """
    client = asset_edit_client
    spam_asset = models.Asset.objects.create(hostname="spam")
    # Verify that hostname is what we set it to
    assert spam_asset.hostname == "spam"
    assert spam_asset.open_ports_tcp == []
    # Send PATCH request
    # Port list is entered by a slob who uses inconsistent separators,
    # not ordered, and repeated values!
    port_string = "8000 80,443, 80"
    response = client.patch(
        f"/api/assets/{spam_asset.id}/",
        json.dumps({"open_ports_tcp": port_string}),
        content_type="application/json",
    )
    assert response.status_code == 200
    # Query for the new version of spam_asset, verify that the list of
    # ports is correct.
    spam_asset = models.Asset.objects.get(id=spam_asset.id)
    # But no fear, the stored list of ports is unique and sorted.
    assert spam_asset.open_ports_tcp == [80, 443, 8000]


@pytest.mark.django_db
def test_patch_asset_open_ports_tcp_list(asset_edit_client):
    """Patching ports with a string of integers.

    We try to be helpful, and sort the resulting list & make it unique.
    """
    client = asset_edit_client
    spam_asset = models.Asset.objects.create(hostname="spam")
    # Verify that hostname is what we set it to
    assert spam_asset.hostname == "spam"
    assert spam_asset.open_ports_tcp == []
    # Send PATCH request
    # Port list is entered by a slob who has repeated values and isn't ordered.
    port_list = [8000, 80, 443, 80]
    response = client.patch(
        f"/api/assets/{spam_asset.id}/",
        json.dumps({"open_ports_tcp": port_list}),
        content_type="application/json",
    )
    assert response.status_code == 200
    # Query for the new version of spam_asset, verify that the list of
    # ports is correct.
    spam_asset = models.Asset.objects.get(id=spam_asset.id)
    # But no fear, the stored list of ports is unique and sorted.
    assert spam_asset.open_ports_tcp == [80, 443, 8000]


@pytest.mark.django_db
def test_patch_asset_open_ports_tcp_list_bad(asset_edit_client):
    """Patching ports with a string of integers.

    We try to be helpful, and sort the resulting list & make it unique.
    """
    client = asset_edit_client
    spam_asset = models.Asset.objects.create(hostname="spam")
    # Verify that hostname is what we set it to
    assert spam_asset.hostname == "spam"
    assert spam_asset.open_ports_tcp == []
    # Send PATCH request
    # Port list has a bad value
    port_list = [80, 443, "foo"]
    response = client.patch(
        f"/api/assets/{spam_asset.id}/",
        json.dumps({"open_ports_tcp": port_list}),
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_patch_asset_open_ports_tcp_bad(asset_edit_client):
    """Patching ports with a string of integers... but they are bad."""
    client = asset_edit_client
    spam_asset = models.Asset.objects.create(hostname="spam")
    # Verify that hostname is what we set it to
    assert spam_asset.hostname == "spam"
    assert spam_asset.open_ports_tcp == []
    # Send PATCH request with bad port
    port_string = "80,443, 66000"
    response = client.patch(
        f"/api/assets/{spam_asset.id}/",
        json.dumps({"open_ports_tcp": port_string}),
        content_type="application/json",
    )
    assert response.status_code == 400
    # Query for the new version of spam_asset, verify that the list of
    # ports is correct.
    spam_asset = models.Asset.objects.get(id=spam_asset.id)
    # Port list is unchanged
    assert spam_asset.open_ports_tcp == []


@pytest.mark.django_db
def test_patch_asset_open_ports_tcp_null(asset_edit_client):
    """Patching ports with Null sets the port list to empty.

    We try to be helpful, and sort the resulting list & make it unique.
    """
    client = asset_edit_client
    spam_asset = models.Asset.objects.create(hostname="spam", open_ports_tcp=[80, 443])
    # Verify that hostname is what we set it to
    assert spam_asset.open_ports_tcp == [80, 443]
    # Send PATCH request
    # Empty port string
    port_string = None
    response = client.patch(
        f"/api/assets/{spam_asset.id}/",
        json.dumps({"open_ports_tcp": port_string}),
        content_type="application/json",
    )
    assert response.status_code == 200
    # Query for the new version of spam_asset, verify that the list of
    # ports is correct.
    spam_asset = models.Asset.objects.get(id=spam_asset.id)
    # Port list is empty
    assert spam_asset.open_ports_tcp == []


@pytest.mark.django_db
def test_patch_asset_open_ports_tcp_empty(asset_edit_client):
    """Patching with empty string sets the port list to empty.

    We try to be helpful, and sort the resulting list & make it unique.
    """
    client = asset_edit_client
    spam_asset = models.Asset.objects.create(hostname="spam", open_ports_tcp=[80, 443])
    # Verify that hostname is what we set it to
    assert spam_asset.open_ports_tcp == [80, 443]
    # Send PATCH request
    # Empty port string
    port_string = ""
    response = client.patch(
        f"/api/assets/{spam_asset.id}/",
        json.dumps({"open_ports_tcp": port_string}),
        content_type="application/json",
    )
    assert response.status_code == 200
    # Query for the new version of spam_asset, verify that the list of
    # ports is correct.
    spam_asset = models.Asset.objects.get(id=spam_asset.id)
    # Port list is empty
    assert spam_asset.open_ports_tcp == []


@pytest.mark.django_db
def test_set_name_empty(asset_edit_client):
    """PATCHing a hostname to an empty string works."""
    client = asset_edit_client
    spam_asset = models.Asset.objects.create(hostname="spam")
    # Verify that hostname is what we set it to
    assert spam_asset.hostname == "spam"
    # Send PATCH request
    _ = client.patch(
        f"/api/assets/{spam_asset.id}/",
        json.dumps({"hostname": ""}),
        content_type="application/json",
    )
    # Query for the new version of spam_asset, verify that its
    # hostname has changed.
    spam_asset = models.Asset.objects.get(id=spam_asset.id)
    assert spam_asset.hostname == ""


@pytest.mark.django_db
def test_set_name_null(asset_edit_client):
    """PATCHing a hostname to `null` works."""
    client = asset_edit_client
    spam_asset = models.Asset.objects.create(hostname="spam")
    # Verify that hostname is what we set it to
    assert spam_asset.hostname == "spam"
    # Send PATCH request
    response = client.patch(
        f"/api/assets/{spam_asset.id}/",
        json.dumps({"hostname": None}),
        content_type="application/json",
    )
    assert response.status_code == 200
    # Query for the new version of spam_asset, verify that its
    # hostname has changed.
    spam_asset = models.Asset.objects.get(id=spam_asset.id)
    assert spam_asset.hostname is None


@pytest.mark.django_db
def test_field_histogram(auth_client):
    """Field histogram works with one field."""
    models.Asset.objects.create(manufacturer="Bar")
    models.Asset.objects.create(manufacturer="Quux")
    models.Asset.objects.create(manufacturer="Foo")
    models.Asset.objects.create(manufacturer="Foo")
    models.Asset.objects.create(manufacturer="Bar")
    models.Asset.objects.create(manufacturer="Foo")

    response = auth_client.get("/api/assets/histogram/", {"field": "manufacturer"})
    qset = response.data

    assert len(qset) == 3
    # Order matters: the histogram is explicitly ordered by highest-count first
    assert [x["manufacturer"] for x in qset] == ["Foo", "Bar", "Quux"]
    assert [x["count"] for x in qset] == [3, 2, 1]


@pytest.mark.django_db
def test_field_histogram_no_field(auth_client):
    """Fail to specify field=<Asset field name> specified: HTTP 400"""
    response = auth_client.get("/api/assets/histogram/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_field_histogram_no_such_field(auth_client):
    """Specify field=<nonsense>: HTTP 400"""
    response = auth_client.get("/api/assets/histogram/", {"field": "asdf"})
    assert response.status_code == 400


@pytest.mark.django_db
def test_api_duplicate_ips(auth_client):
    """Check for duplicate IP addresses in the asset population."""
    response = auth_client.get("/api/assets/duplicate_ips/")
    assert response.status_code == 200
    assert response.json() == []

    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(manufacturer="Foo", ip_address=None)
    response = auth_client.get("/api/assets/duplicate_ips/")
    assert response.status_code == 200
    assert response.json() == [
        ["1.2.3.4", 3],
        ["1.2.3.5", 2],
    ]


@pytest.mark.django_db
def test_api_duplicate_ips_one(auth_client):
    """Check for duplicate IP addresses in the asset population."""
    response = auth_client.get("/api/assets/duplicate_ips/")
    assert response.status_code == 200
    assert response.json() == []

    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(manufacturer="Foo", ip_address=None)
    response = auth_client.get("/api/assets/duplicate_ips/?ip_address=1.2.3.4")
    assert response.status_code == 200
    assert response.json() == [
        ["1.2.3.4", 3],
    ]


@pytest.mark.django_db
@pytest.mark.xfail(
    raises=AssertionError,
    reason="not allowed to spell out 'exact' in URL for some reason.",
)
def test_api_duplicate_ips_one_spell_exact(auth_client):
    """Check for duplicate IP addresses in the asset population."""
    response = auth_client.get("/api/assets/duplicate_ips/")
    assert response.status_code == 200
    assert response.json() == []

    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.4")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(ip_address="1.2.3.5")
    models.Asset.objects.create(manufacturer="Foo", ip_address=None)
    response = auth_client.get("/api/assets/duplicate_ips/?ip_address__exact=1.2.3.4")
    assert response.status_code == 200
    assert response.json() == [
        ["1.2.3.4", 3],
    ]


@pytest.mark.django_db
def test_api_duplicate_ips_one_prefix_robust(auth_client):
    """Check for duplicate IP addresses in the asset population."""
    response = auth_client.get("/api/assets/duplicate_ips/")
    assert response.status_code == 200
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
    assert response.status_code == 200
    assert response.json() == [
        ["1.2.3.4", 3],
    ]


@pytest.mark.django_db
def test_fetch_by_os(auth_client):
    """Assets can be fetched by OS field."""
    a1 = models.Asset.objects.create(os="Windows XP")
    a2 = models.Asset.objects.create(os="WinXP")
    a3 = models.Asset.objects.create(os="XP")

    response = auth_client.get("/api/assets/?os__iexact=XP")
    assert response.status_code == 200
    js = response.json()
    assert js["count"] == 1
    assert js["results"][0]["id"] == a3.id

    response = auth_client.get("/api/assets/?os__icontains=XP")
    assert response.status_code == 200
    js = response.json()
    assert js["count"] == 3
    ids = set(x["id"] for x in js["results"])
    assert ids == set([a1.id, a2.id, a3.id])

    response = auth_client.get("/api/assets/?os__istartswith=win")
    assert response.status_code == 200
    js = response.json()
    assert js["count"] == 2
    ids = set(x["id"] for x in js["results"])
    assert ids == set([a1.id, a2.id])


@pytest.mark.django_db
def test_app_sw_version_needs_update(auth_client):
    """Test whether assets need software updates."""
    oldest = models.Asset.objects.create(
        manufacturer="Foo", model="Bar", app_sw_version="1.2.3"
    )
    newer = models.Asset.objects.create(
        manufacturer="Foo", model="Bar", app_sw_version="1.2.4"
    )
    newest = models.Asset.objects.create(
        manufacturer="Foo", model="Bar", app_sw_version="1.2.5"
    )

    response = auth_client.get(f"/api/assets/{oldest.id}/needs_sw_update/")
    assert response.status_code == 200
    assert response.json()["latest"] == newest.app_sw_version
    assert response.json()["needs_update"] is True

    response = auth_client.get(f"/api/assets/{newer.id}/needs_sw_update/")
    assert response.status_code == 200
    assert response.json()["latest"] == newest.app_sw_version
    assert response.json()["needs_update"] is True

    response = auth_client.get(f"/api/assets/{newest.id}/needs_sw_update/")
    assert response.status_code == 200
    assert response.json()["latest"] == newest.app_sw_version
    assert response.json()["needs_update"] is False


@pytest.mark.django_db
def test_nonsense_app_sw_version_needs_update(auth_client):
    """Test whether a silly asset needs an update."""
    a = models.Asset.objects.create(
        manufacturer="Foo", model="Bar", app_sw_version="Henrik Holm"
    )
    resp = auth_client.get(f"/api/assets/{a.id}/needs_sw_update/")
    assert resp.json()["needs_update"] is False

    # create another asset; how does it sort? parsable > legacy...
    models.Asset.objects.create(
        manufacturer="Foo", model="Bar", app_sw_version="3.54.5"
    )
    resp = auth_client.get(f"/api/assets/{a.id}/needs_sw_update/")
    assert resp.json()["needs_update"] is True


@pytest.mark.django_db
def test_app_sw_version_not_needs_update(auth_client):
    """Test whether two equal assets need updates."""
    a1 = models.Asset.objects.create(
        manufacturer="Foo", model="Bar", app_sw_version="1.2.3"
    )
    a2 = models.Asset.objects.create(
        manufacturer="Foo", model="Bar", app_sw_version="1.2.3"
    )

    response1 = auth_client.get(f"/api/assets/{a1.id}/needs_sw_update/")
    response2 = auth_client.get(f"/api/assets/{a2.id}/needs_sw_update/")
    assert response1.status_code == response2.status_code == 200
    assert response1.json()["latest"] == "1.2.3"
    assert response1.json()["needs_update"] is False
    assert response2.json()["latest"] == "1.2.3"
    assert response2.json()["needs_update"] is False


@pytest.mark.django_db
def test_app_sw_no_version_needs_update(auth_client):
    """Test whether assets without software versions need updates."""
    asset = models.Asset.objects.create(manufacturer="Foo", model="Bar")
    response = auth_client.get(f"/api/assets/{asset.id}/needs_sw_update/")
    assert response.status_code == 200
    assert response.json()["latest"] is None
    assert response.json()["versions_in_use"] == {}
    assert response.json()["needs_update"] is False


@pytest.mark.django_db
def test_api_create_asset_mac_autofill_nic(asset_edit_client):
    """Create an asset with NIC vendor."""
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps({"mac_address": "34:36:3b:c4:7d:ec"}),
        content_type="application/json",
    )
    assert response.status_code == 201  # 201 = Created
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["mac_address"] == "34:36:3b:c4:7d:ec"
    assert asset["nic_vendor"] == "Apple, Inc."


@pytest.mark.django_db
def test_api_create_asset_mac_reject_nic(asset_edit_client):
    """Provided NIC vendor will be silently ignored."""
    client = asset_edit_client
    response = client.post(
        "/api/assets/",
        json.dumps(
            {
                "mac_address": "34:36:3b:c4:7d:ec",
                "nic_vendor": "Appletown USA",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201  # 201 = Created
    assets = client.get("/api/assets/")
    assert assets.data["count"] == 1
    asset = assets.data["results"].pop()
    assert asset["mac_address"] == "34:36:3b:c4:7d:ec"
    assert asset["nic_vendor"] == "Apple, Inc."


@pytest.mark.django_db
def test_upsert_create(asset_edit_client):
    """Create a new asset via upsert endpoint."""
    macaddr = "00:03:b1:b5:b6:48"
    response = asset_edit_client.post(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": macaddr,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201  # Created
    assert response.data["mac_address"] == macaddr
    assert response.data["nic_vendor"] == "Hospira Inc."
    assert models.Asset.objects.count() == 1
    asset = models.Asset.objects.get()
    assert asset.mac_address == macaddr


@pytest.mark.django_db
def test_upsert_update(asset_edit_client):
    """Update an existing asset via upsert endpoint."""
    # Create existing asset in database
    models.Asset.objects.create(mac_address="11:22:33:44:55:66")
    response = asset_edit_client.post(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": "11:22:33:44:55:66",
                "ip_address": "10.0.0.1",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200  # OK
    assert response.data["mac_address"] == "11:22:33:44:55:66"
    assert response.data["ip_address"] == "10.0.0.1"
    assert models.Asset.objects.count() == 1
    asset = models.Asset.objects.get()
    assert asset.mac_address == "11:22:33:44:55:66"
    assert str(asset.ip_address) == "10.0.0.1"


@pytest.mark.django_db
def test_upsert_no_mac_address(asset_edit_client):
    """Upsert endpoint ignores calls that lack a MAC address."""
    response = asset_edit_client.post(
        "/api/assets/upsert/",
        json.dumps(
            {
                "ip_address": "10.0.0.1",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 412  # Precondition failed
    assert models.Asset.objects.count() == 0


@pytest.mark.django_db
def test_upsert_no_mac_address_duplicate(asset_edit_client):
    """Call upsert endpoint twice, with the same IP address.

    The first call contains a MAC address and creates an asset.  The second
    call lacks a MAC address and is ignored.
    """
    response = asset_edit_client.post(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": "11:22:33:44:55:66",
                "ip_address": "10.0.0.1",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201  # Created
    response = asset_edit_client.post(
        "/api/assets/upsert/",
        json.dumps(
            {
                "ip_address": "10.0.0.1",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 412  # Precondition failed
    assert models.Asset.objects.count() == 1


@pytest.mark.django_db
def test_upsert_ipv6(asset_edit_client):
    """Call upsert endpoint with an ipv6 address.

    There is no "ipv6_address" field on an Asset model.  The /api/upsert/
    endpoint should silently ignore this field.
    """
    response = asset_edit_client.post(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": "11:22:33:44:55:66",
                "ipv6_address": "0:0:0:0:0:ffff:a00:1",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201  # Created
    assert models.Asset.objects.count() == 1


@pytest.mark.django_db
def test_upsert_many_fields(asset_edit_client):
    """Call upsert endpoint with a fields typically provided by sniffer."""
    response = asset_edit_client.post(
        "/api/assets/upsert/",
        json.dumps(
            {
                "ipv4_address": "10.0.0.155",
                "ipv6_address": "",
                "open_port_tcp": "",
                "connect_port_tcp": "",
                "mac_address": "00:03:b1:b5:b6:48",
                "identifier": "Hospira Plum A+",
                "provenance": "HL7 PRT-10",
                "last_seen": "2018-12-21T11:39:05.897236-08:00",
                "client_id": "ohm.virta.io",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201  # Created
    assert models.Asset.objects.count() == 1


@pytest.mark.django_db
def test_upsert_ipv4(asset_edit_client):
    """Call upsert endpoint with a "ipv4_address" field.

    There is no "ipv4_address" field on an Asset model.  The /api/upsert/
    endpoint should coerce an "ipv4_address" field "ip_address".
    """
    response = asset_edit_client.post(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": "11:22:33:44:55:66",
                "ipv4_address": "10.0.0.1",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201  # Created
    assert response.data["ip_address"] == "10.0.0.1"
    asset = models.Asset.objects.get()
    assert str(asset.ip_address) == "10.0.0.1"


@pytest.mark.django_db
def test_upsert_bad_key(asset_edit_client):
    """Call upsert endpoint with a bad key in the JSON."""
    with pytest.raises(django.core.exceptions.FieldDoesNotExist):
        _ = asset_edit_client.post(
            "/api/assets/upsert/",
            json.dumps(
                {
                    "mac_address": "11:22:33:44:55:66",
                    "ipv12345_address": "10.0.0.1",  # Bad key!
                }
            ),
            content_type="application/json",
        )


@pytest.mark.django_db
def test_upsert_open_port_tcp(asset_edit_client):
    """Call upsert endpoint with a "open_port_tcp" field.

    There is no "open_tcp_port" field on an Asset model.  The /api/upsert/
    endpoint should append the port to the "open_ports_tcp" array field.
    """
    response = asset_edit_client.post(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": "11:22:33:44:55:66",
                "open_port_tcp": "80",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201  # Created
    assert response.data["open_ports_tcp"] == [80]
    asset = models.Asset.objects.get()
    assert asset.open_ports_tcp == [80]


@pytest.mark.django_db
def test_upsert_identifier(asset_edit_client):
    """Call upsert endpoint with a "identifier" field.

    Coerce "identifier" field to "name".
    """
    response = asset_edit_client.post(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": "11:22:33:44:55:66",
                "identifier": "Alaris 8100",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201  # Created
    assert response.data["name"] == "Alaris 8100"
    asset = models.Asset.objects.get()
    assert asset.name == "Alaris 8100"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "date_range, num_assets",
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
def test_asset_date_range(date_range, num_assets, auth_client):
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
    assert res.status_code == 200
    assert res.data["count"] == 7

    with freeze_time("2018-06-30 13:00:00", tz_offset=0):
        res = auth_client.get(f"/api/assets/?date_range={date_range}")
        assert res.data["count"] == num_assets


@pytest.mark.django_db
def test_external_key_non_connector(db, auth_client):
    """Test that external_links/ detail route doesn't barf on non-connector
    external key.
    """
    foobar = models.Asset.objects.create(name="Foobar")
    foobar.external_keys = {"ECN": "12345"}
    foobar.save()
    assert foobar.external_keys["ECN"] == "12345"

    res = auth_client.get(f"/api/assets/{foobar.id}/external_links/")
    assert res.status_code == 200
    assert len(res.data) == 1
    assert res.data["ECN"] == "12345"
