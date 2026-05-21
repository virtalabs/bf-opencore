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
    cpe: str
    role: str
    upstream_api: str
    hostname: str
    mac_address: str
    serial_number: str
    location: dict[str, str]
    status: str
    vendor_id: str
    utilization: list[dict[str, int]]

    def __init__(self, asset: Asset):
        self.ip = str(asset.ip_address) if asset.ip_address else ""
        self.network_segment = (
            ""  # TODO(taylorcochran): get network segment from asset.network_qset()
        )
        self.cpe = ""  # TODO(taylorcochran): get cpe from asset.cpe_qset()
        self.role = str(asset.category) if asset.category else ""
        self.upstream_api = f"{settings.BASE_URL}/api/assets/{asset.id}/"
        self.hostname = asset.hostname or ""
        # Coerce to str so payload is JSON-serializable
        # (Asset uses netaddr.EUI / InetAddress)
        self.mac_address = str(asset.mac_address) if asset.mac_address else ""
        self.serial_number = asset.serial_number or ""
        self.location = {"facility": "", "building": "", "floor": "", "room": ""}
        self.status = "Active"
        self.vendor_id = str(asset.nic_vendor) if asset.nic_vendor else ""
        self.utilization = _project_usage(asset)

    def to_dict(self):
        """Return a JSON-serializable dict (for json.dumps or requests)."""
        return asdict(self)


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

    def to_dict(self):
        """Return a JSON-serializable dict (for json.dumps or requests)."""
        base = asdict(self)
        for key in self._INTERNAL_KEYS:
            base.pop(key, None)
        base["items"] = [item.to_dict() for item in self.items]
        base["next"] = self.next
        base["previous"] = self.previous
        return base

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
        assets = Asset.objects.filter(modified__gte=request.since)
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
