import math
import uuid
from collections.abc import Generator
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import ClassVar

from django.apps import apps
from django.conf import settings
from django.db import models

from blueflow.models import Asset


def _to_iso(value: datetime | str | None) -> str | None:
    """Coerce a datetime to ISO-8601; pass strings/None through unchanged."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class ViperWebhookJob(models.Model):
    """Persisted record of an incoming Viper webhook request."""

    class Status(models.TextChoices):
        PENDING = "pending"
        STARTED = "started"
        FINISHED = "finished"
        ERROR = "error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    # callback = models.URLField() # noqa: ERA001
    callback = models.CharField(blank=False, null=False)
    since = models.DateTimeField()
    before = models.DateTimeField(null=True, blank=True)
    request_body = models.JSONField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.id}"


@dataclass
class ViperWebhookRequest:
    """Data for a viper webhook."""

    callback: str
    since: datetime | str  # iso8601 on the wire; DRF hands us a datetime
    before: datetime | str | None  # iso8601 on the wire; DRF hands us a datetime
    max_pages: int
    page_size: int

    def to_dict(self):
        """Return a JSON-serializable dict (for json.dumps or requests)."""
        base = asdict(self)
        base["since"] = _to_iso(self.since)
        base["before"] = _to_iso(self.before)
        return base


def _project_usage(asset: Asset) -> list[dict[str, int]]:
    """Project an asset's Usage rows into Viper's utilization shape.

    Monday-first length-7 list of {str(hour): count} dicts; zero-count hours
    stripped. Mirrors ``AssetSerializer.get_usage`` so both integrations agree
    on the wire shape.
    """
    days: list[dict[str, int]] = [{} for _ in range(7)]
    for usage in asset.usage.all():
        bucket = days[usage.day_of_week]
        for hour in range(24):
            count = getattr(usage, f"hour_{hour:02d}")
            if count > 0:
                bucket[str(hour)] = count
    return days


@dataclass
class ViperAsset:
    """Data for a viper asset."""

    ip: str
    network_segment: str
    _cpe: str
    role: str
    upstream_api: str
    hostname: str
    mac_address: str
    serial_number: str
    location: dict[str, str]
    status: str
    vendor_id: str
    utilization: list[dict[str, int]]
    product: str

    def __init__(self, asset: Asset):
        self.ip = str(asset.ip_address) if asset.ip_address else ""
        self.network_segment = (
            ""  # TODO(taylorcochran): get network segment from asset.network_qset()
        )
        self._cpe = ""  # TODO(taylorcochran): get cpe from asset.cpe_qset()
        self.role = str(asset.category) if asset.category else ""
        self.upstream_api = f"{settings.BASE_URL}/api/assets/{asset.id}/"
        self.hostname = asset.hostname or ""
        # Coerce to str so payload is JSON-serializable
        # (Asset uses netaddr.EUI / InetAddress)
        self.mac_address = str(asset.mac_address) if asset.mac_address else ""
        self.serial_number = asset.serial_number or ""
        self.location = {"facility": "", "building": "", "floor": "", "room": ""}
        self.status = "Active"
        if not asset.id:
            raise ValueError("How did we get an asset with no id?")
        self.vendor_id = str(asset.id)
        self.utilization = _project_usage(asset)
        self.product = str(asset.product) if asset.product else ""

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict for Viper integrationUpload.

        Uses camelCase keys per Viper's ``assetInputSchema``.  ``role`` is
        omitted when ``Asset.category`` is unset — Viper treats empty strings
        as invalid (``.min(1)``) and stores null.  ``vendorId`` is
        ``Asset.manufacturer`` (TapirXL ``vendor`` → BlueFlow manufacturer).
        """
        out: dict = {
            "ip": self.ip,
            "upstreamApi": self.upstream_api,
            "vendorId": self.vendor_id,
            "status": self.status,
            "utilization": self.utilization,
        }
        if self.hostname:
            out["hostname"] = self.hostname
        if self.mac_address:
            out["macAddress"] = self.mac_address
        if self.serial_number:
            out["serialNumber"] = self.serial_number
        if self.network_segment:
            out["networkSegment"] = self.network_segment
        if self.cpe:
            out["cpe"] = self.cpe
        if self.role:
            out["role"] = self.role
        if any(self.location.values()):
            out["location"] = self.location
        return out

    @property
    def cpe(self) -> str:
        """Builds the cpe string from the asset dataclass.

        Cached after first build. Lots of this data is mocked atm, we'll need
        to get specifics from Cassidy for the demo.
        """
        if self._cpe:
            return self._cpe
        unknown = "*"
        self._cpe = ":".join(
            [
                "cpe",  # always the same
                # TODO(taylorcochran): figure out what version cass wants
                "2.3",  # version
                "h",  # 'part' # h for now but: https://en.wikipedia.org/wiki/Common_Platform_Enumeration#part
                self.vendor_id or unknown,  # vendor
                self.product or unknown,  # product # do we want something different ?
                "-",
                unknown,  # version of product?
                unknown,  # point release / minor versions
                unknown,  # any additional information beyond version for id
                unknown,  # lang is empty for now
                # en-US -- https://datatracker.ietf.org/doc/html/rfc5646
                unknown,  # "edition" i.e. MS desktop vs MS Server etc
                unknown,  # 'target' wiki ex: `windows_2003` & `ipod_touch`
                unknown,  # 'target_hw', but really the cpu architecture type
            ]
        )
        return self._cpe


@dataclass
class ViperWebhookResponse:
    """Response for a viper webhook."""

    items: list[ViperAsset]
    page: int
    page_size: int
    total_count: int
    total_pages: int
    since: datetime | str
    request_id: str = ""
    before: datetime | str | None = None
    # settings?
    webhook_path: str = "/api/viper/webhook/"

    # Keys held on the dataclass for internal use (URL generation, retry
    # bookkeeping) but stripped before the payload goes on the wire to Viper.
    _INTERNAL_KEYS: ClassVar[tuple[str, ...]] = (
        "since",
        "before",
        "request_id",
        "webhook_path",
    )

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (for json.dumps or requests)."""
        return {
            "items": [item.to_dict() for item in self.items],
            "page": self.page,
            "pageSize": self.page_size,
            "totalCount": self.total_count,
            "totalPages": self.total_pages,
            "next": self.next,
            "previous": self.previous,
        }

    def _gen_page(self, page: int) -> str:
        """Generate a page URL for on the page number, page size, and last sync time."""
        since = _to_iso(self.since)
        params = f"page={page}&page_size={self.page_size}&since={since}"
        if self.before:
            params += f"&before={_to_iso(self.before)}"
        return f"{settings.BASE_URL}{self.webhook_path}?{params}"

    @property
    def next(self) -> str | None:
        """Return the URL to the next page."""
        if self.page >= self.total_pages:
            return None
        if hasattr(self, "_next"):
            return self._next
        self._next = self._gen_page(self.page + 1)
        return self._next

    @property
    def previous(self) -> str | None:
        """Return the URL to the previous page."""
        if self.page <= 1:
            return None
        if hasattr(self, "_previous"):
            return self._previous
        self._previous = self._gen_page(self.page - 1)
        return self._previous


@dataclass
class ViperWebhookResponseList:
    @staticmethod
    def from_request(
        request: ViperWebhookRequest,
        request_id: str = "",
    ) -> Generator[ViperWebhookResponse, None, None]:
        Asset = apps.get_model("blueflow", "Asset")
        assets = Asset.objects.filter(modified__gte=request.since).prefetch_related(
            "usage",
        )
        if request.before:
            assets = assets.filter(modified__lte=request.before)
        assets = assets.order_by("modified").all()
        total_count = assets.count()
        total_pages = math.ceil(total_count / request.page_size)
        page = 1
        for i in range(0, len(assets), request.page_size):
            if page > request.max_pages:
                err = f"Max pages exceeded: {request.max_pages}"
                raise ValueError(err)
            assets_chunk = [ViperAsset(a) for a in assets[i : i + request.page_size]]
            response = ViperWebhookResponse(
                items=assets_chunk,
                page=page,
                page_size=request.page_size,
                total_count=total_count,
                total_pages=total_pages,
                since=request.since,
                before=request.before,
                request_id=request_id,
            )
            page += 1
            yield response
