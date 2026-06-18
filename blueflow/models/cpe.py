"""Shared CPE 2.3 string construction for asset-like sources.

A single builder so the CPE *format* (field order, padding, unknown sentinel)
lives in exactly one place. The two sources that need a CPE expose vendor /
product under different names and with different normalization, so the builder
selects the right fields by structurally matching on the source's type:

- ``Asset`` (ORM model) — raw ``manufacturer`` / ``model``.
- ``ViperAsset`` (outbound DTO) — pre-normalized ``vendor`` / ``product``.
"""

# Value used for every CPE field we don't (yet) populate. Per the CPE 2.3
# formatted-string spec, ``*`` means "any".
UNKNOWN_CPE_VALUE: str = "*"


def build_cpe(source: object, *, unknown: str = UNKNOWN_CPE_VALUE) -> str:
    """Build a CPE 2.3 string from an asset-like ``source``.

    The vendor and product slots are chosen by matching on ``source``'s type;
    every remaining slot is stubbed with ``unknown`` (default
    :data:`UNKNOWN_CPE_VALUE`) until real version / edition / target data is
    available. ``unknown`` is keyword-only so call sites read explicitly.
    """
    # Imported lazily: ``Asset`` is a lower import layer than ``ViperAsset``
    # (which imports it), so binding either at module top would form a cycle.
    from blueflow.models.asset import Asset  # noqa: PLC0415
    from blueflow.models.viper import ViperAsset  # noqa: PLC0415

    match source:
        case Asset():
            vendor = str(source.manufacturer or unknown)
            product = str(source.model or unknown)
        case ViperAsset():
            vendor = source.vendor or unknown
            product = source.product or unknown
        case _:
            msg = f"Cannot build a CPE from {type(source).__name__}"
            raise TypeError(msg)

    return ":".join(
        [
            "cpe",  # always the same
            "2.3",  # CPE version
            "h",  # 'part' — h(ardware) for now: https://en.wikipedia.org/wiki/Common_Platform_Enumeration#part
            vendor,
            product,
            "-",  # product version separator
            unknown,  # version of product
            unknown,  # point release / minor version
            unknown,  # any additional id info beyond version
            unknown,  # lang, e.g. en-US (RFC 5646)
            unknown,  # edition, e.g. MS desktop vs MS server
            unknown,  # target, e.g. windows_2003 / ipod_touch
            unknown,  # target_hw — cpu architecture type
        ]
    )
