"""Topology snapshot endpoint (read-only, contract-level stub).

Returns a single snapshot matching the minimal_network-topology schema
(v0.1.0-minimal, attached to issue #135). No backing model yet — the
canned empty payload exists to lock the OpenAPI contract immediately.
Real derivation from Asset / NetworkEndpoint is a follow-up.
"""

import uuid
from datetime import UTC, datetime

from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from blueflow.models import constants


class TopologyInterfaceSerializer(serializers.Serializer):
    """A network interface observed on a device."""

    id = serializers.CharField()
    mac_address = serializers.RegexField(
        regex=r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$",
        required=False,
        allow_null=True,
    )
    ipv4_address = serializers.IPAddressField(
        protocol="IPv4", required=False, allow_null=True
    )
    ipv6_address = serializers.IPAddressField(
        protocol="IPv6", required=False, allow_null=True
    )


class TopologyServiceSerializer(serializers.Serializer):
    """A port/protocol pair observed receiving traffic on an asset."""

    port = serializers.IntegerField(
        min_value=constants.PORT_MIN, max_value=constants.PORT_MAX
    )
    protocol = serializers.ChoiceField(choices=["tcp", "udp"])


class TopologyAssetSerializer(serializers.Serializer):
    """A device observed on the network (topology-level wire shape)."""

    id = serializers.CharField(help_text="Hostname; sourced from Asset.hostname.")
    manufacturer = serializers.CharField(required=False, allow_null=True)
    interfaces = TopologyInterfaceSerializer(many=True)
    services = TopologyServiceSerializer(many=True, required=False)


class TopologyConnectionSerializer(serializers.Serializer):
    """An observed traffic flow between two assets."""

    src_asset_id = serializers.CharField()
    dst_asset_id = serializers.CharField()
    dst_port = serializers.IntegerField(
        min_value=constants.PORT_MIN, max_value=constants.PORT_MAX
    )
    protocol = serializers.ChoiceField(choices=["tcp", "udp"])
    direction = serializers.ChoiceField(choices=["unidirectional", "bidirectional"])


class TopologySerializer(serializers.Serializer):
    """Root topology snapshot."""

    schema_version = serializers.SerializerMethodField()
    snapshot_id = serializers.UUIDField()
    timestamp = serializers.DateTimeField()
    assets = TopologyAssetSerializer(many=True)
    connections = TopologyConnectionSerializer(many=True, required=False)

    @extend_schema_field({"type": "string", "const": "0.1.0-minimal"})
    def get_schema_version(self, _obj):
        return "0.1.0-minimal"


class TopologyView(APIView):
    """Read-only topology snapshot endpoint (stub payload)."""

    @extend_schema(responses=TopologySerializer)
    def get(self, request):  # noqa: ARG002
        return Response(
            {
                "schema_version": "0.1.0-minimal",
                "snapshot_id": str(uuid.uuid4()),
                "timestamp": datetime.now(UTC).isoformat(),
                "assets": [],
                "connections": [],
            }
        )
