"""Unit tests for the shared CPE builder (``blueflow.models.cpe.build_cpe``).

The builder is exercised directly so failures point at the format / dispatch
logic rather than at any caller. The ``Asset`` arm needs no database — the
builder only reads ``manufacturer`` / ``model`` off an in-memory instance — so
those cases stay pure; the ``ViperAsset`` arm requires a saved asset.
"""

import pytest

from blueflow.models import Asset
from blueflow.models.cpe import UNKNOWN_CPE_VALUE, build_cpe
from blueflow.models.viper import ViperAsset

CPE_FIELD_COUNT = 13
BRIGHTSPEED_CPE = "cpe:2.3:h:gehealthcare:brightspeed_elite_select:-:*:*:*:*:*:*:*"


def test_build_cpe_from_asset_uses_manufacturer_and_model():
    """The Asset arm fills the vendor / product slots from raw model fields."""
    asset = Asset(manufacturer="gehealthcare", model="brightspeed_elite_select")
    assert build_cpe(asset) == BRIGHTSPEED_CPE


def test_build_cpe_unknown_slots_default_to_star():
    """An asset with no manufacturer / model stubs every slot with ``*``."""
    assert build_cpe(Asset()) == "cpe:2.3:h:*:*:-:*:*:*:*:*:*:*"


def test_build_cpe_emits_thirteen_colon_separated_fields():
    """Guards the CPE 2.3 shape against accidental slot add/remove."""
    assert len(build_cpe(Asset()).split(":")) == CPE_FIELD_COUNT


def test_build_cpe_unknown_kwarg_overrides_sentinel():
    """The ``unknown`` kwarg replaces the fallback in every stubbed slot."""
    assert build_cpe(Asset(), unknown="?") == "cpe:2.3:h:?:?:-:?:?:?:?:?:?:?"


def test_build_cpe_unknown_defaults_to_module_constant():
    """Omitting ``unknown`` uses the canonical sentinel."""
    assert f":{UNKNOWN_CPE_VALUE}:" in build_cpe(Asset())


def test_build_cpe_unknown_is_keyword_only():
    """Passing the sentinel positionally is a hard error, not a silent arg."""
    with pytest.raises(TypeError):
        build_cpe(Asset(), "?")


def test_build_cpe_rejects_unsupported_source():
    """The ``case _`` arm refuses types it has no field mapping for."""
    with pytest.raises(TypeError, match="Cannot build a CPE from str"):
        build_cpe("not-an-asset")


def test_build_cpe_dispatch_diverges_by_type(db):
    """Same asset, two sources: Asset keeps raw casing/spaces, Viper normalizes.

    Proves the type-based dispatch picks the right field set — ``ViperAsset``
    lowercases and de-spaces vendor/product in ``__init__``, ``Asset`` does not.
    """
    asset = Asset.objects.create(
        hostname="cpe-dispatch.example.com",
        ip_address="10.0.0.9",
        manufacturer="ACME Corp",
        model="Smart Pump 3000",
    )
    raw = "cpe:2.3:h:ACME Corp:Smart Pump 3000:-:*:*:*:*:*:*:*"
    normalized = "cpe:2.3:h:acmecorp:smart_pump_3000:-:*:*:*:*:*:*:*"
    assert build_cpe(asset) == raw
    assert build_cpe(ViperAsset(asset)) == normalized
