from rest_framework import serializers

from blueflow import models


class NetworkInterfaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.NetworkInterface
        fields = ("mac_address", "ipv4", "ipv6")
