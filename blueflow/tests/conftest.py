"""Pytest configuration for blueflow app-level tests.

All tests require PostgreSQL (set DATABASE_URL in test settings).
"""

from dataclasses import dataclass

import pytest
from django.test import override_settings
from model_bakery import baker
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from blueflow import models
from blueflow.tests.factories import make_user

# ---------------------------------------------------------------------------
# Role-scoped API clients (alias to auth_client when no per-resource perms)
# ---------------------------------------------------------------------------


@pytest.fixture
def asset_edit_client(auth_client):
    """Return API client with user that can create/edit assets.

    Alias to auth_client in blueflow.
    """
    return auth_client


@pytest.fixture
def nwk_authorized_client(auth_client):
    """Return API client with user allowed to manage networks.

    Alias to auth_client in blueflow.
    """
    return auth_client


@pytest.fixture
def biomed_client(auth_client):
    """Return API client with biomed role. Alias to auth_client in blueflow."""
    return auth_client


@pytest.fixture
def custom_field_edit_client(auth_client):
    """Return API client with user allowed to edit custom field names.

    Alias to auth_client in blueflow.
    """
    return auth_client


@pytest.fixture
def token_auth_client(db, enable_core_switch):
    """Return API client authenticated via Token header."""
    user = make_user(username="scanner")
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


# ---------------------------------------------------------------------------
# Data fixtures (moved from inline test modules)
# ---------------------------------------------------------------------------


@pytest.fixture
def media_root(tmp_path):
    """Use tmp_path for MEDIA_ROOT so attachment tests don't touch real filesystem."""
    media = tmp_path / "media"
    media.mkdir()
    with override_settings(MEDIA_ROOT=str(media)):
        yield media


@pytest.fixture
def cleandb(db):
    """Remove custom fields added by migrations.

    For example, the "location" custom field is added by a migration.  These
    tests assume starting without it.
    """
    models.AssetCustomFieldName.objects.all().delete()


@pytest.fixture
def cfield(cleandb):
    """Prepare fixtures: an asset, custom field names, and a custom field value."""
    asset = baker.make("Asset", hostname="foo.com")
    baker.make("NetworkInterface", system=asset)
    _ = models.AssetCustomFieldName.objects.create(field_name="sparkliness")
    shiny_field = models.AssetCustomFieldName.objects.create(field_name="shinyness")
    _ = models.AssetCustomField.objects.create(
        field=shiny_field,
        asset=asset,
        value_text="rather dull",
    )


@pytest.fixture
def completables(db):
    """Sample assets and other items to be completed."""
    models.Asset.objects.create(mac_address="88:aa:bb:cc:dd:ee")
    models.Asset.objects.create(
        manufacturer="ACME Inc.", model="Instant Tunnel", serial_number="WILE-E-1234"
    )
    models.Asset.objects.create(
        manufacturer="ACME", model="Instant Tunnel", serial_number="RR-6789"
    )
    w95 = models.Asset.objects.create(os="Windows 95", ip_address="10.2.3.5")
    models.Tag.objects.create(name="ACME products")
    models.Tag.objects.create(name="FooTag")
    barv = models.Vulnerability.objects.create(name="foo", synopsis="Bar Baz Quux")
    models.AssetVulnerability.objects.create(asset=w95, vulnerability=barv)
    grp = models.Group.objects.create(name="Bargle")
    models.AssetGroup.objects.create(asset=w95, group=grp)
    blorp = models.Network.objects.create(name="BlorpNet")
    blorp.cidr = ["10.2.3.0/24"]
    blorp.save()


@pytest.fixture
def complete_us(db):
    """Sample assets for autocomplete field tests."""
    mfmods = {
        "Foo": ["One", "Two", "Three"],
        "Bar": ["Four", "Five", "Six"],
    }
    assets = []
    for manuf, model_list in mfmods.items():
        assets.extend(
            models.Asset(manufacturer=manuf, model=model_name)
            for model_name in model_list
        )
    models.Asset.objects.bulk_create(assets)


@dataclass(frozen=True)
class AssetGroupsFixture:
    """Bundle of two assets, three groups, and the three join rows linking them.

    TODO(taylorcochran) replace this with model bakery
    """

    asset_a: models.Asset
    asset_b: models.Asset
    group_red: models.Group
    group_green: models.Group
    group_yellow: models.Group
    link_red_a: models.AssetGroup
    link_green_a: models.AssetGroup
    link_green_b: models.AssetGroup


@pytest.fixture
def asset_groups(db):
    """Set up some assets and groups."""
    asset_a = models.Asset.objects.create(hostname="foo.com")
    asset_b = models.Asset.objects.create(hostname="bar.com")
    group_red = models.Group.objects.create(name="red")
    group_green = models.Group.objects.create(name="green")
    group_yellow = models.Group.objects.create(name="yellow")
    return AssetGroupsFixture(
        asset_a=asset_a,
        asset_b=asset_b,
        group_red=group_red,
        group_green=group_green,
        group_yellow=group_yellow,
        link_red_a=models.AssetGroup.objects.create(group=group_red, asset=asset_a),
        link_green_a=models.AssetGroup.objects.create(group=group_green, asset=asset_a),
        link_green_b=models.AssetGroup.objects.create(group=group_green, asset=asset_b),
    )


# Alias for tests that refer to completables as "acme_assets" (e.g. test_saved_search)
@pytest.fixture
def acme_assets(completables):
    """Alias for completables (same fixture data)."""
    return completables
