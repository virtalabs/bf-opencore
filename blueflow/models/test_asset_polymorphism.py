import pytest
from model_bakery import baker

from blueflow import models


@pytest.fixture
def create_asset() -> None:
    _ = baker.make(models.Asset)


def test_asset_is_system(create_asset) -> None:
    asset = models.Asset.objects.first()
    assert issubclass(asset.__class__, models.System)


def test_asset_is_queryable_from_system(create_asset) -> None:
    system = models.System.objects.first()
    assert hasattr(system, "asset")


def test_asset_has_attributes_after_query(create_asset) -> None:
    system = models.System.objects.first()
    assert hasattr(system, "asset")
    asset = system.asset
    assert hasattr(asset, "name")
    assert hasattr(asset, "ip_address")
