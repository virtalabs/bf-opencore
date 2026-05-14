"""drf-spectacular integrations for ``django-netfields`` and related REST fields."""

from typing import TYPE_CHECKING, Any

import netfields.rest_framework as nrf
from drf_spectacular.extensions import OpenApiSerializerFieldExtension
from drf_spectacular.openapi import AutoSchema
from netfields import InetAddressField as NetInetModelField
from netfields import MACAddressField as NetMacModelField
from rest_framework import serializers

if TYPE_CHECKING:
    from django.db.models import Field as DjangoModelField


def ipv4_ipv6_string_schema(*, allow_null: bool) -> dict[str, Any]:
    """OpenAPI dual-stack textual IP representation."""
    schema: dict[str, Any] = {
        "oneOf": [
            {"type": "string", "format": "ipv4"},
            {"type": "string", "format": "ipv6"},
        ],
    }
    if allow_null:
        schema["nullable"] = True
    return schema


class BlueflowSpectacularAutoSchema(AutoSchema):
    """Routes ``netfields`` model columns through REST serializer introspection."""

    def _map_model_field(self, model_field: "DjangoModelField", direction):
        if isinstance(model_field, NetInetModelField):
            ser = nrf.InetAddressField(allow_null=model_field.null)
            dir_ = direction or "response"
            return self._map_serializer_field(ser, dir_)
        if isinstance(model_field, NetMacModelField):
            ser = nrf.MACAddressField(allow_null=model_field.null)
            dir_ = direction or "response"
            return self._map_serializer_field(ser, dir_)
        return super()._map_model_field(model_field, direction)


class InetAddressOpenApi(OpenApiSerializerFieldExtension):
    """OpenAPI for ``netfields.rest_framework.InetAddressField``."""

    target_class = nrf.InetAddressField

    def map_serializer_field(self, _auto_schema: AutoSchema, _direction: str):
        return ipv4_ipv6_string_schema(allow_null=self.target.allow_null)


class MacAddressOpenApi(OpenApiSerializerFieldExtension):
    """OpenAPI for ``netfields.rest_framework.MACAddressField``."""

    target_class = nrf.MACAddressField

    def map_serializer_field(self, _auto_schema: AutoSchema, _direction: str):
        schema: dict[str, Any] = {"type": "string"}
        if self.target.allow_null:
            schema["nullable"] = True
        return schema


class NetfieldsBackedModelDRFField(OpenApiSerializerFieldExtension):
    """``serializers.ModelField`` shim when the DB column is from ``netfields``."""

    target_class = serializers.ModelField
    priority = 1

    def map_serializer_field(self, auto_schema: AutoSchema, direction: str):
        mf = self.target.model_field
        allow_null = bool(getattr(mf, "null", False))
        dir_ = direction or "response"
        if isinstance(mf, NetInetModelField):
            return ipv4_ipv6_string_schema(allow_null=allow_null)
        if isinstance(mf, NetMacModelField):
            sch: dict[str, Any] = {"type": "string"}
            if allow_null:
                sch["nullable"] = True
            return sch
        return auto_schema._map_serializer_field(  # noqa: SLF001
            self.target,
            dir_,
            bypass_extensions=True,
        )
