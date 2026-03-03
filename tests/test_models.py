"""Tests for bf_opencore models (mirrors bf_opencore/models)."""

import pytest


def test_asset_model(db):
    """Smoke test: Asset can be created."""
    from bf_opencore.models import Asset

    asset = Asset.objects.create()
    assert asset.pk is not None
    assert Asset.objects.filter(pk=asset.pk).exists()


def test_connector_model(db):
    """Smoke test: Connector model exists and has expected attributes."""
    from bf_opencore.models import Connector

    assert hasattr(Connector, "objects")


def test_tag_model(db):
    """Smoke test: Tag model exists and has expected attributes."""
    from bf_opencore.models import Tag

    assert hasattr(Tag, "objects")
