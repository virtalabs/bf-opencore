import netfields
from django.db import models

from . import system


class ExternalSystem(system.System):
    """ExternalSystem represents any asset like thing outside of the owned network.

    ExternalSystem instances are intended to be queried and managed by its parent.
    ex:
    s = System.objects.first()
    external = getattr(s, "external", None)
    """

    hostname = models.CharField(null=True, unique=True)  # noqa: DJ001
    ip_address = netfields.InetAddressField(
        store_prefix_length=False,
        null=True,
        verbose_name="IP address",
    )
