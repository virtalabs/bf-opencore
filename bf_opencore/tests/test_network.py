"""Network API tests."""

import json

import pytest

from bf_opencore import models

# models do have 'objects' member, but it's being lazy loaded


def test_create_empty_network(nwk_authorized_client):
    """Creating a network without a name is not allowed."""
    response = nwk_authorized_client.post(
        "/api/networks/",
        # json.dumps({'name': None}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_create_named_network(nwk_authorized_client):
    """Create a network without CIDR via the API.

    Ideally, this should not be legal... but it's not straightforward to
    prevent at the API level.
    """
    response = nwk_authorized_client.post(
        "/api/networks/", json.dumps({"name": "spam"}), content_type="application/json"
    )
    assert response.status_code == 201
    networks = models.Network.objects.all()
    assert len(networks) == 1
    network = networks.first()
    assert network.name == "spam"
    assert network.cidr == []


@pytest.mark.xfail(reason="Open-core has no role-based write permissions")
def test_create_named_network_unauth(auth_client):
    """Don't create a network with unauthorized client."""
    response = auth_client.post(
        "/api/networks/", json.dumps({"name": "spam"}), content_type="application/json"
    )
    assert response.status_code == 403
    assert models.Network.objects.count() == 0


CIDR_TEST_DATA = [
    # 3 simple tests (one IP or CIDR supplied)
    # 3 slightly trickier tests (2 IPs supplied
    #   but results in one CIDR)
    # 1 tricky test: 2 IPs that result in 2 CIDRs
    #
    # Test data is interspersed, since one of the tests below uses the *change*
    ("10.0.1.2", ["10.0.1.2/32"]),
    ("10.0.1.2, 10.0.1.3", ["10.0.1.2/31"]),
    ("", []),
    ("10.0.1.2,10.0.1.3 ", ["10.0.1.2/31"]),
    ("10.0.1.2/31", ["10.0.1.2/31"]),
    ("10.0.1.2, 10.0.1.4", ["10.0.1.2/32", "10.0.1.4/32"]),
    ("10.0.1.2/32", ["10.0.1.2/32"]),
    ("10.0.1.2/31 10.0.1.3 ", ["10.0.1.2/31"]),
]


@pytest.mark.parametrize("supplied_cidr, resulting_cidr", CIDR_TEST_DATA)
def test_create_network_then_cidr(supplied_cidr, resulting_cidr, nwk_authorized_client):
    """Create a network then add one or more CIDR."""
    response = nwk_authorized_client.post(
        "/api/networks/", json.dumps({"name": "spam"}), content_type="application/json"
    )
    assert response.status_code == 201
    response = nwk_authorized_client.patch(
        response.data["url"],
        json.dumps({"cidr": supplied_cidr}),
        content_type="application/json",
    )
    # assert response.content == '{}'
    assert response.status_code == 200
    network = models.Network.objects.first()
    assert network.name == "spam"
    assert network.cidr == resulting_cidr


@pytest.mark.parametrize("supplied_cidr, resulting_cidr", CIDR_TEST_DATA)
def test_get_cidr(supplied_cidr, resulting_cidr, nwk_authorized_client):
    """Create a network + CIDR, then get CIDR."""
    # using same test data, ignoring result
    response = nwk_authorized_client.post(
        "/api/networks/", json.dumps({"name": "spam"}), content_type="application/json"
    )
    assert response.status_code == 201
    response = nwk_authorized_client.patch(
        response.data["url"],
        json.dumps({"cidr": supplied_cidr}),
        content_type="application/json",
    )
    assert response.status_code == 200
    response = nwk_authorized_client.get("/api/cidrs/", content_type="application/json")
    assert response.status_code == 200


def test_delete_cidr(nwk_authorized_client):
    """Create a network, add CIDR, delete CIDR."""
    response = nwk_authorized_client.post(
        "/api/networks/", json.dumps({"name": "spam"}), content_type="application/json"
    )
    assert response.status_code == 201
    network = models.Network.objects.first()
    assert network.cidr == []

    nwk_url = response.data["url"]
    response = nwk_authorized_client.patch(
        nwk_url, json.dumps({"cidr": "10.0.1.2"}), content_type="application/json"
    )
    assert response.status_code == 200
    network = models.Network.objects.first()
    assert network.cidr == ["10.0.1.2/32"]

    response = nwk_authorized_client.patch(
        nwk_url, json.dumps({"cidr": ""}), content_type="application/json"
    )
    assert response.status_code == 200
    network = models.Network.objects.first()
    assert network.cidr == []


def test_change_cidr_one(nwk_authorized_client):
    """Create a network, add CIDR, change CIDR."""
    response = nwk_authorized_client.post(
        "/api/networks/", json.dumps({"name": "spam"}), content_type="application/json"
    )
    assert response.status_code == 201
    nwk_url = response.data["url"]
    response = nwk_authorized_client.patch(
        nwk_url, json.dumps({"cidr": "10.0.1.2"}), content_type="application/json"
    )
    assert response.status_code == 200
    network = models.Network.objects.first()
    assert network.cidr == ["10.0.1.2/32"]
    response = nwk_authorized_client.patch(
        nwk_url, json.dumps({"cidr": "10.0.1.3"}), content_type="application/json"
    )
    assert response.status_code == 200
    network = models.Network.objects.first()
    assert network.cidr == ["10.0.1.3/32"]


@pytest.mark.parametrize("test_case", range(1, len(CIDR_TEST_DATA)))
def test_change_cidr(nwk_authorized_client, test_case):
    """Create a network, add CIDR, change CIDR.

    Using the first entry in CIDR_TEST_DATA as the *base*, then changing
    to others.
    """
    response = nwk_authorized_client.post(
        "/api/networks/", json.dumps({"name": "spam"}), content_type="application/json"
    )
    assert response.status_code == 201
    network = models.Network.objects.first()
    assert network.cidr == []

    nwk_url = response.data["url"]
    response = nwk_authorized_client.patch(
        nwk_url,
        json.dumps({"cidr": CIDR_TEST_DATA[test_case - 1][0]}),
        content_type="application/json",
    )
    assert response.status_code == 200
    network = models.Network.objects.first()
    assert network.cidr == CIDR_TEST_DATA[test_case - 1][1]

    response = nwk_authorized_client.patch(
        nwk_url,
        json.dumps({"cidr": CIDR_TEST_DATA[test_case][0]}),
        content_type="application/json",
    )
    assert response.status_code == 200
    network = models.Network.objects.first()
    assert network.cidr == CIDR_TEST_DATA[test_case][1]


@pytest.mark.xfail(
    raises=ValueError,
    reason="Create Nwk w/CIDR is not yet implemented, fails "
    "with the following error: \n\n"
    "'ValueError: save() prohibited to prevent data "
    "loss due to unsaved related object 'network'. \n\n"
    "Documented in Github issue #1444.",
)
def test_create_cidr_network(nwk_authorized_client):
    """Create network with CIDR in one go."""
    response = nwk_authorized_client.post(
        "/api/networks/",
        json.dumps({"name": "spam", "cidr": "10.0.1.2"}),
        content_type="application/json",
    )
    # Don't expect this create to work
    assert response.status_code == 201
    # network = models.Network.objects.first()
    # assert network.name == 'spam'
    # assert network.cidr == ['10.0.1.2']


@pytest.mark.xfail(
    raises=AssertionError,
    reason="There's a bug in CIDR validation code.  Documented in Github issue #1443.",
)
def test_patch_bad_cidr(nwk_authorized_client):
    """Modify the CIDR in an existing network."""
    # Create a network
    response = nwk_authorized_client.post(
        "/api/networks/", json.dumps({"name": "spam"}), content_type="application/json"
    )
    assert response.status_code == 201

    # Update the CIDR with a bad value
    response = nwk_authorized_client.patch(
        response.data["url"],
        json.dumps({"cidr": "spam"}),
        content_type="application/json",
    )
    assert response.status_code == 400  # This should fail


def test_cidr_bad_json(nwk_authorized_client):
    """Verify list of CIDRs is valid JSON."""
    # Create a network
    response = nwk_authorized_client.post(
        "/api/networks/", json.dumps({"name": "spam"}), content_type="application/json"
    )
    assert response.status_code == 201
    # Add CIDR
    response = nwk_authorized_client.patch(
        response.data["url"],
        json.dumps({"cidr": "192.168.0.0/16"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    # Parse list of CIDRs, should work without throwing an exception
    cidr_list = response.data["cidr"]
    assert cidr_list[0] == "192.168.0.0/16"


################################################################
# Test Asset - Network connections


def test_asset_in_network_old_api(nwk_authorized_client):
    """Ensure we can determine network membership."""
    dummy_asset = models.Asset.objects.create(ip_address="10.0.0.1")
    network = models.Network.objects.create()
    network.cidr = ["10.0.0.0/24"]
    response = nwk_authorized_client.get(f"/api/networks/{network.id}/assets/")
    assert response.status_code == 404


def test_asset_in_network_new_api(nwk_authorized_client):
    """Ensure we can determine network membership."""
    asset = models.Asset.objects.create(ip_address="10.0.0.1")
    dummy_asset_out_of_network = models.Asset.objects.create(ip_address="10.0.1.1")
    network = models.Network.objects.create()
    network.cidr = ["10.0.0.0/24"]
    response = nwk_authorized_client.get(f"/api/assets/?network={network.id}")
    assets = response.data["results"]
    assert len(assets) == 1
    assert assets[0]["id"] == asset.id


def test_asset_big_network(nwk_authorized_client):
    """Ensure these things work also in other networks."""
    asset_ips = [
        "192.168.218.1",
        "192.168.218.32",
        "192.168.218.38",
        "192.168.218.29",
        "192.168.218.24",
        "192.168.218.6",
        "192.168.218.4",
        "192.168.218.102",
        "192.168.218.101",
    ]
    asset = {}
    for ip_address in asset_ips:
        asset[ip_address] = models.Asset.objects.create(ip_address=ip_address)
    network_big = models.Network.objects.create(name="big")
    network_big.cidr = ["192.168.218.0/24"]
    network_small = models.Network.objects.create(name="small")
    network_small.cidr = ["192.168.218.100/30"]
    response_small = nwk_authorized_client.get(
        f"/api/assets/?network={network_small.id}"
    )
    assets = response_small.data["results"]
    assert len(assets) == 2
    assert {a["ip_address"] for a in assets} == set(
        ["192.168.218.101", "192.168.218.102"]
    )
    response_big = nwk_authorized_client.get(f"/api/assets/?network={network_big.id}")
    assets = response_big.data["results"]
    assert len(assets) == 9
    assert {a["ip_address"] for a in assets} == set(asset_ips)
