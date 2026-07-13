import netfields

from . import system


class ExternalSystem(system.System):
    """ExternalSystem represents any asset like thing outside of the owned network.

    ExternalSystem instances are intended to be queried and managed by it's parent.
    ex:
    s = System.objects.first()
    external = getattr(s, "external", None)
    """

    ip_address = netfields.InetAddressField(
        store_prefix_length=False,
        null=True,
        verbose_name="IP address",
    )
