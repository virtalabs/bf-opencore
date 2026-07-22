"""Tests for Asset.hostname stable-identity behavior (#137).

Three layers of enforcement, each tested in isolation so a failure in one
layer is caught at the cheapest possible level:

1. Serializer (AssetUpsertSerializer) — input validation before the DB
2. View (the upsert action) — hostname-conflict detection logic
3. Database (UniqueConstraint + CheckConstraint) — the actual contract,
   which catches anything bypassing the Python layers entirely.
"""

import json

import pytest
from django.db import IntegrityError, transaction
from model_bakery import baker
from rest_framework import status
from rest_framework.test import APIClient

from blueflow import models
from blueflow.serializers import AssetUpsertSerializer

MAC_A = "AA:BB:CC:DD:EE:FF"
MAC_B = "11:22:33:44:55:66"
# AssetUpsertSerializer.manufacturer is required=True; supply it on every
# payload that should pass field validation and reach the hostname logic.
MFR = "Acme"


# ---------------------------------------------------------------------------
# Layer 1 — Serializer (AssetUpsertSerializer.hostname)
# ---------------------------------------------------------------------------


def test_upsert_serializer_rejects_empty_hostname() -> None:
    """allow_blank=False means '' is a validation error, not a NULL placeholder."""
    serializer = AssetUpsertSerializer(data={"mac_address": MAC_A, "hostname": ""})
    assert not serializer.is_valid()
    assert "hostname" in serializer.errors


def test_upsert_serializer_accepts_null_hostname() -> None:
    """External callers (VRL/TapirXL) may send hostname=null; serializer must accept.

    The model is nullable on purpose — see test_db_allows_multiple_null_hostnames
    for why. The wire-level acceptance of `null` is part of the upsert contract.
    """
    serializer = AssetUpsertSerializer(
        data={"mac_address": MAC_A, "hostname": None, "manufacturer": MFR}
    )
    assert serializer.is_valid(), serializer.errors


def test_upsert_serializer_accepts_missing_hostname() -> None:
    """Omitting hostname entirely is also 'absent' and must pass validation."""
    serializer = AssetUpsertSerializer(data={"mac_address": MAC_A, "manufacturer": MFR})
    assert serializer.is_valid(), serializer.errors


def test_upsert_serializer_accepts_real_hostname() -> None:
    """A non-empty hostname passes validation."""
    serializer = AssetUpsertSerializer(
        data={"mac_address": MAC_A, "hostname": "foo.example", "manufacturer": MFR},
    )
    assert serializer.is_valid(), serializer.errors


# ---------------------------------------------------------------------------
# Layer 2 — View (upsert action conflict logic)
# ---------------------------------------------------------------------------


def test_upsert_creates_asset_with_hostname(asset_edit_client: APIClient) -> None:
    """Happy path: new asset with a fresh hostname returns 201."""
    response = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(
            {"mac_address": MAC_A, "hostname": "foo.example", "manufacturer": MFR}
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["hostname"] == "foo.example"


def test_upsert_same_mac_same_hostname_is_legitimate_noop(
    asset_edit_client: APIClient,
) -> None:
    """Re-upserting the same (MAC, hostname) pair is an update, not a conflict."""
    asset = baker.make("Asset", hostname="foo.example", manufacturer=MFR)
    interface = baker.make("NetworkInterface", system=asset, mac_address=MAC_A)
    response = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": interface.mac_address,
                "hostname": "foo.example",
                "manufacturer": asset.manufacturer,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_200_OK


def test_upsert_same_mac_new_hostname_is_legitimate_update(
    asset_edit_client: APIClient,
) -> None:
    """Same MAC + new hostname is a hostname change, not a conflict."""
    asset = baker.make("Asset", hostname="old.example")
    _ = baker.make("NetworkInterface", system=asset, mac_address=MAC_A)
    response = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(
            {"mac_address": MAC_A, "hostname": "new.example", "manufacturer": MFR}
        ),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_200_OK
    asset.refresh_from_db()
    assert asset.hostname == "new.example"


def test_upsert_without_hostname_does_not_check_conflicts(
    asset_edit_client: APIClient,
) -> None:
    """Conflict detection is gated on truthy hostname; must not fire on absent."""
    payload = {
        "mac_address": MAC_B,
        "manufacturer": MFR,
    }
    response = asset_edit_client.put(
        "/api/assets/upsert/",
        payload,
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED


# ---------------------------------------------------------------------------
# Layer 3 — Database (UniqueConstraint + CheckConstraint)
# ---------------------------------------------------------------------------
#
# These tests use Asset.objects.create() and Asset.objects.update() directly,
# bypassing the serializer and view layers entirely. They prove the database
# is the actual contract — anything writing to the DB (raw SQL, bulk_create,
# direct scanner code) gets blocked.


def test_db_rejects_duplicate_hostname() -> None:
    """The unique index on Asset.hostname blocks duplicates at the DB layer."""
    models.Asset.objects.create(hostname="foo.example")
    with pytest.raises(IntegrityError), transaction.atomic():
        models.Asset.objects.create(hostname="foo.example")


def test_db_allows_multiple_null_hostnames() -> None:
    """Load-bearing: NULL hostnames must coexist under the unique index.

    Postgres treats every NULL as distinct in unique indexes, which is the
    SOLE reason `hostname` is `null=True` despite the project's general
    preference for non-nullable CharFields. If this test breaks, do NOT
    change `unique=True` or `null=True` without rewriting the upsert
    conflict-detection logic in AssetUpsertSerializer / the upsert action.
    """
    a = models.Asset.objects.create(hostname=None)
    b = models.Asset.objects.create(hostname=None)
    assert a.id != b.id


def test_db_rejects_empty_hostname_on_insert() -> None:
    """The CheckConstraint blocks empty-string hostnames at insert time."""
    with pytest.raises(IntegrityError), transaction.atomic():
        models.Asset.objects.create(hostname="")


def test_db_rejects_empty_hostname_on_update() -> None:
    """CheckConstraint also catches UPDATEs (e.g. QuerySet.update bypassing save)."""
    asset = models.Asset.objects.create(hostname="foo.example")
    with pytest.raises(IntegrityError), transaction.atomic():
        models.Asset.objects.filter(pk=asset.pk).update(hostname="")


def test_db_constraint_error_includes_constraint_name() -> None:
    """The constraint name is part of the public contract; renames must update tests."""
    with pytest.raises(IntegrityError) as exc_info, transaction.atomic():
        models.Asset.objects.create(hostname="")
    assert "asset_hostname_not_empty_when_set" in str(exc_info.value)
