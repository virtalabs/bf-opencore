"""Pytest configuration for bf_opencore app-level tests. All tests require PostgreSQL (set DATABASE_URL in test settings)."""

from collections import namedtuple

import pytest

# ---------------------------------------------------------------------------
# Role-scoped API clients (alias to auth_client when no per-resource perms)
# ---------------------------------------------------------------------------


@pytest.fixture
def asset_edit_client(auth_client):
    """API client with user that can create/edit assets. Alias to auth_client in open-core."""
    return auth_client


@pytest.fixture
def nwk_authorized_client(auth_client):
    """API client with user allowed to manage networks. Alias to auth_client in open-core."""
    return auth_client


@pytest.fixture
def biomed_client(auth_client):
    """API client with biomed role. Alias to auth_client in open-core."""
    return auth_client


@pytest.fixture
def custom_field_edit_client(auth_client):
    """API client with user allowed to edit custom field names. Alias to auth_client in open-core."""
    return auth_client


@pytest.fixture
def pulse_feed_auth_client(auth_client):
    """API client with user allowed to delete/close pulse feed items. Alias to auth_client in open-core."""
    return auth_client

@pytest.fixture
def tapirx_token_client(db, enable_core_switch):
    """API client authenticated via Token header, mirroring Tapirx's auth method."""
    from rest_framework.test import APIClient
    from rest_framework.authtoken.models import Token

    from bf_opencore.tests.factories import make_user

    user = make_user(username="tapirx")
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
    from django.test import override_settings

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
    from bf_opencore import models

    models.AssetCustomFieldName.objects.all().delete()


@pytest.fixture
def cfield(cleandb):
    """Prepare some things for reuse: an asset, custom field names, and a custom field value."""
    from bf_opencore import models

    asset = models.Asset.objects.create(hostname="foo.com")
    sparkly_field = models.AssetCustomFieldName.objects.create(field_name="sparkliness")
    shiny_field = models.AssetCustomFieldName.objects.create(field_name="shinyness")
    custom_field = models.AssetCustomField.objects.create(
        field=shiny_field, asset=asset, value_text="rather dull",
    )
    cfield_tuple = namedtuple(
        "cfield_tuple",
        ["asset", "sparkly_field", "shiny_field", "custom_field",],
    )
    return cfield_tuple(asset, sparkly_field, shiny_field, custom_field,)


@pytest.fixture
def asset_vulnerabilities(db):
    """Set up some database objects to test asset-vulnerability relations."""
    from bf_opencore import models

    asset = models.Asset.objects.create(hostname="foo.com")
    asset_2 = models.Asset.objects.create(hostname="bar.com")
    models.Vulnerability.objects.create(name="eggs")
    vulnerability_spam = models.Vulnerability.objects.create(name="spam")
    vulnerability_red = models.Vulnerability.objects.create(name="red")
    vulnerability_green = models.Vulnerability.objects.create(name="green")
    models.AssetVulnerability.objects.create(
        vulnerability=vulnerability_red, asset=asset
    )
    models.AssetVulnerability.objects.create(
        vulnerability=vulnerability_green, asset=asset
    )
    models.AssetVulnerability.objects.create(
        vulnerability=vulnerability_spam, asset=asset_2
    )
    return (asset, vulnerability_red, vulnerability_green)


@pytest.fixture
def completables(db):
    """Sample assets and other items to be completed."""
    from bf_opencore import models

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
    from bf_opencore import models

    mfmods = {
        "Foo": ["One", "Two", "Three"],
        "Bar": ["Four", "Five", "Six"],
    }
    assets = []
    for manuf, model_list in mfmods.items():
        for model_name in model_list:
            assets.append(
                models.Asset(manufacturer=manuf, model=model_name),
            )
    models.Asset.objects.bulk_create(assets)


@pytest.fixture
def asset_groups(db):
    """Set up some assets and groups."""
    from bf_opencore import models

    asset_a = models.Asset.objects.create(hostname="foo.com")
    asset_b = models.Asset.objects.create(hostname="bar.com")
    group_red = models.Group.objects.create(name="red")
    group_green = models.Group.objects.create(name="green")
    group_yellow = models.Group.objects.create(name="yellow")
    agra = models.AssetGroup.objects.create(group=group_red, asset=asset_a)
    agga = models.AssetGroup.objects.create(group=group_green, asset=asset_a)
    aggb = models.AssetGroup.objects.create(group=group_green, asset=asset_b)
    ag = namedtuple("AssetGroups", "aa, ab, gr, gg, gy, agra, agga, aggb")
    return ag(
        aa=asset_a,
        ab=asset_b,
        gr=group_red,
        gg=group_green,
        gy=group_yellow,
        agra=agra,
        agga=agga,
        aggb=aggb,
    )


@pytest.fixture
def pulse_feed_items(db):
    """Set up some pulse feed items to play with."""
    from django.utils import timezone

    from bf_opencore import models

    models.PulseFeedItem.objects.create(
        external_pulse_id=12, date_last_updated=timezone.now()
    )
    models.PulseFeedItem.objects.create(
        external_pulse_id=23, date_last_updated=timezone.now()
    )
    models.PulseFeedItem.objects.create(
        external_pulse_id=34, date_last_updated=timezone.now()
    )


# Alias for tests that refer to completables as "acme_assets" (e.g. test_saved_search)
@pytest.fixture
def acme_assets(completables):
    """Alias for completables (same fixture data)."""
    return completables
