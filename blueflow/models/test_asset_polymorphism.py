from blueflow import models


def test_asset_is_system(db) -> None:
    asset = models.Asset.objects.first()
    assert issubclass(asset.__class__, models.System)


def test_asset_is_queryable_from_system(db) -> None:
    system = models.System.objects.first()
    assert hasattr(system, "asset")


def test_asset_has_attributes_after_query(db) -> None:
    system = models.System.objects.first()
    assert hasattr(system, "asset")
    asset = system.asset
    assert hasattr(asset, "name")
    assert hasattr(asset, "ip")
