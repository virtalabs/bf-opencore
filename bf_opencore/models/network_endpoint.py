"""Model for devices seen on the network."""

from django.db import models
from django.core.exceptions import ValidationError
import django.contrib.postgres.fields as pg_fields
from django.db.models.signals import post_save

from netfields import MACAddressField, InetAddressField

from django.apps import apps
from bf_opencore.utils import DisableSignals


class NetworkEndpointManager(models.Manager):
    """Manager maintains priority."""

    def normalize_and_get(self, **kwargs):
        """Return one canonical NetworkEndpoint, deleting ambigious matches."""
        fields_by_priority = ["mac_address", "ipv4_address", "ipv6_address"]
        f = models.Q()
        for field in fields_by_priority:
            if field in kwargs and kwargs[field]:
                f |= models.Q(**{field: kwargs[field]})

        results = super().filter(f)

        if results.count() == 0:
            NetworkEndpoint = apps.get_model('bf_opencore', 'NetworkEndpoint')
            raise NetworkEndpoint.DoesNotExist()
        if results.count() == 1:
            return results.first()
        else:
            # if there is more than one match, mac_address must be set
            chosen = results.get(mac_address=kwargs["mac_address"])
            others = results.exclude(pk=chosen.pk)
            for endpoint in others:
                success = chosen.merge(endpoint)
                if success:
                    # merged the details we care about
                    endpoint.delete()
                else:
                    # IP conflicts exist, clear them
                    if endpoint.ipv4_address == kwargs.get("ipv4_address"):
                        endpoint.ipv4_address = None
                    if endpoint.ipv6_address == kwargs.get("ipv6_address"):
                        endpoint.ipv6_address = None
                    endpoint.save()
                chosen.save()
            return chosen

    def update_or_create_by_priority(self, defaults=None, **kwargs):
        """Return or create a NetworkEndpoint, prefering Mac address."""
        if not defaults:
            defaults = {}
        NetworkEndpoint = apps.get_model('bf_opencore', 'NetworkEndpoint')
        try:
            match = self.normalize_and_get(**kwargs)
            for key, value in defaults.items():
                setattr(match, key, value)
            created = False
        except NetworkEndpoint.DoesNotExist:
            new_values = kwargs
            new_values.update(defaults)
            match = NetworkEndpoint(**new_values)
            created = True

        match.save()
        return (match, created)


class EndpointSuggestion(models.Model):
    """An inferred connection between an Asset and a NetworkEndpoint."""

    asset = models.ForeignKey('Asset', on_delete=models.CASCADE)
    network_endpoint = models.ForeignKey('NetworkEndpoint',
                                         on_delete=models.CASCADE)
    confidence = models.SmallIntegerField(default=0)
    confidence_limit = models.SmallIntegerField(default=0)
    evidence = models.JSONField(default=list)


class NetworkEndpoint(models.Model):
    """Holds an device observed on the network."""

    class Meta:  # noqa
        unique_together = (
            ('mac_address', 'ipv4_address'),
            ('mac_address', 'ipv6_address'))

    mac_address = MACAddressField(unique=True, null=True, blank=True)
    ipv4_address = InetAddressField(store_prefix_length=False,
                                    blank=True, null=True, unique=True)
    ipv6_address = InetAddressField(store_prefix_length=False,
                                    blank=True, null=True, unique=True)

    # user indicated this NetworkEndpoint definitely refers to one asset
    _user_asset_match = models.ForeignKey('Asset',
                                          on_delete=models.SET_NULL,
                                          related_name='network_endpoints',
                                          blank=True, null=True)

    # user indicated that the following guesses were wrong
    _asset_match_blacklist = pg_fields.ArrayField(models.IntegerField(),
                                                  default=list, blank=True)

    first_seen = models.DateTimeField(auto_now_add=True, editable=False)
    last_seen = models.DateTimeField(auto_now=True)

    # port can look like: "80/TCP", "ICMP" and "62000/UDP"
    transmit_ports = pg_fields.ArrayField(models.CharField(max_length=9),
                                          default=list, blank=True)
    receive_ports = pg_fields.ArrayField(models.CharField(max_length=9),
                                         default=list, blank=True)

    max_confidence = models.SmallIntegerField(default=0)

    # override objects to use our custom manager
    objects = NetworkEndpointManager()

    def add_transmit_ports(self, ports):
        """Set transmit_ports to transmit_ports union ports."""
        self.transmit_ports = list(set(self.transmit_ports) | set(ports))

    def add_receive_ports(self, ports):
        """Set receive_ports = receive_ports union ports."""
        self.receive_ports = list(set(self.receive_ports) | set(ports))

    @property
    def asset(self):
        """Get a definite asset associated with this endpoint.

        Return the Asset set using the setter, the asset that matches IP or
        MAC if only one such asset matches, or None - in that order of
        preference.
        """
        if self._user_asset_match:
            # if corresponding asset was set manually, use it
            return self._user_asset_match
        else:
            sieve = models.Q()
            if self.mac_address:
                sieve |= models.Q(mac_address=self.mac_address)
            if self.ipv4_address:
                sieve |= models.Q(ip_address=self.ipv4_address)
            if self.ipv6_address:
                sieve |= models.Q(ip_address=self.ipv6_address)

            Asset = apps.get_model('bf_opencore', 'Asset')
            mac_matches = Asset.objects.filter(sieve)

            if mac_matches.count() == 1:
                # there is one, unambigious corresponding asset
                return mac_matches.first()
            else:
                # there are multiple possible corresponding assets, or none
                return None

    @asset.setter
    def asset(self, value):
        """Set a definite asset that this endpoint is.

        Will clear all suggestions.
        """
        self._user_asset_match = value
        EndpointSuggestion = apps.get_model('bf_opencore', 'EndpointSuggestion')
        EndpointSuggestion.objects.filter(
            network_endpoint=self).delete()

    @property
    def suggestions(self):
        """Return a list of guesses as to which Assets are this Endpoint.

        Return None if asset has been set, never return assets in blacklist.
        """
        EndpointSuggestion = apps.get_model('bf_opencore', 'EndpointSuggestion')
        return (EndpointSuggestion.objects.filter(network_endpoint=self)
                .order_by('-confidence'))

    @property
    def blacklist(self):
        """Return IDs of Assets that are definitely not this endpoint."""
        return self._asset_match_blacklist

    @blacklist.setter
    def blacklist(self, value):
        """Set the blacklist of Assets that are definitely not this endpoint.

        Deletes all EndpointSuggestions linking this Endpoint to the provided
        Asset IDs.
        """
        self._asset_match_blacklist = value
        EndpointSuggestion = apps.get_model('bf_opencore', 'EndpointSuggestion')
        EndpointSuggestion.objects.filter(network_endpoint=self,
                                          asset__in=value).delete()
        self.update_suggestions()

    def compare(self, asset):
        """Return a report on likelihood of this endpoint being the asset."""
        confidence = 0
        evidence = []

        matching_criteria = [
            {
                "reason": "Devices on same network",
                "value": lambda asset: (self.ipv4_address and
                                        asset.network_qset()
                                        .filter(cidr__cidr__net_contains=self
                                                .ipv4_address)
                                        .first()
                                        .name),
                "weight": lambda asset: 1,
                "max_weight": 1,
                "test": lambda asset: (self.ipv4_address and
                                       asset.network_qset()
                                       .filter(cidr__cidr__net_contains=self
                                               .ipv4_address)
                                       .exists())
            },
            {
                "reason": "Devices on same network",
                "value": lambda asset: (self.ipv6_address and
                                        asset.network_qset()
                                        .filter(cidr__cidr__net_contains=self
                                                .ipv6_address)
                                        .first()
                                        .name),
                "weight": lambda asset: 1,
                "max_weight": 1,
                "test": lambda asset: (self.ipv6_address and
                                       asset.network_qset()
                                       .filter(cidr__cidr__net_contains=self
                                               .ipv6_address)
                                       .exists())
            },
            {
                "reason": "Shared MAC address range",
                "value": lambda asset: "{}*".format(str(self.mac_address)[:9]),
                "weight": lambda asset: 4,
                "max_weight": 4,
                "test": lambda asset: (self.mac_address and asset
                                       .mac_address and
                                       self.mac_address.value >> 24 == asset
                                       .mac_address.value >> 24)
            },
            {
                "reason": "Shared TCP ports",
                "value": lambda asset: {int(port.strip("/TCP")) for port
                                        in self.receive_ports
                                        if port.endswith("/TCP")}.intersection(
                                            set(asset.open_ports_tcp)),
                "weight": lambda asset: min(
                    len({int(port.strip("/TCP")) for port
                         in self.receive_ports
                         if port.endswith("/TCP")}
                        .intersection(set(asset.open_ports_tcp))),
                    3),
                "max_weight": 3,
                "test": lambda asset: (not {int(port.strip("/TCP"))
                                            for port in self.receive_ports
                                            if port.endswith("/TCP")}
                                       .isdisjoint(set(asset.open_ports_tcp)))
            }
        ]

        for criteria in matching_criteria:
            if criteria["test"](asset):
                confidence += criteria["weight"](asset)
                evidence.append({
                    "reason": str(criteria["reason"]),
                    "value": str(criteria["value"](asset))
                })

        return {
            "confidence": confidence,
            "confidence_limit": sum([x["max_weight"] for x
                                     in matching_criteria]),
            "evidence": evidence,
            "asset": asset,
        }

    def update_suggestions(self):
        """Update EndpointSuggestion models for this NetworkEndpoint."""
        self.clean_fields()

        if self.asset:
            return

        # start at no confidence
        self.max_confidence = 0

        Asset = apps.get_model('bf_opencore', 'Asset')
        for asset in (Asset.objects
                      .exclude(id__in=self.blacklist)):
            report = self.compare(asset)
            confidence = int(report["confidence"])
            if confidence:
                # only record if confidence > 0
                EndpointSuggestion = apps.get_model('bf_opencore', 'EndpointSuggestion')
                change, _ = EndpointSuggestion.objects.update_or_create(
                    asset=asset, network_endpoint=self)
                change.confidence = confidence
                change.evidence = report["evidence"]
                change.confidence_limit = report["confidence_limit"]
                change.save()

                if confidence > self.max_confidence:
                    self.max_confidence = confidence
                    # avoid infinite recursion
                    with DisableSignals([post_save]):
                        self.save()

    def clean(self):
        """Ensure model is valid."""
        if not (self.mac_address or self.ipv4_address or self.ipv6_address):
            raise ValidationError("A MAC or IP address must be provided")

    def merge(self, other):
        """
        Merge with another NetworkEndpoint.

        If MAC and IP addresses don't conflict, incorporates transmit_ports and
        receive_ports from NetworkEndpoint. If they are unset in self,
        incorporates "ipv4_address", "ipv6_address", and "mac_address" from
        NetworkEndpoint.

        Returns true if merge was successful (no conflicts).
        """
        identifying_fields = ["mac_address", "ipv4_address", "ipv6_address"]

        conflict = False
        for field in identifying_fields:
            conflict = conflict or (getattr(self, field) and
                                    getattr(other, field) and
                                    getattr(self, field) !=
                                    getattr(other, field))

        if conflict:
            return False

        for field in identifying_fields:
            if not getattr(self, field):
                value = getattr(other, field)
                setattr(self, field, value)

        self.add_transmit_ports(other.transmit_ports)
        self.add_receive_ports(other.receive_ports)
        return True

    def __hash__(self):
        """Hash this model."""
        # combination of Model type and PK is unique
        return hash((self.__class__, self.pk))

    def __eq__(self, other):
        """Equal if both NetworkEndpoint and primary key is equal."""
        return isinstance(other, self.__class__) and self.pk == other.pk

    def __str__(self):  # noqa
        return "Netflow endpoint with MAC {} and IP {}".format(
            self.mac_address,
            (self.ipv4_address, self.ipv6_address)
        )
