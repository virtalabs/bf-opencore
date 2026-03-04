import math
from collections.abc import Generator
from dataclasses import asdict, dataclass

from django.apps import apps
from django.conf import settings

from bf_opencore.models import Asset


@dataclass
class ViperWebhookRequest:
    """Data for a viper webhook."""

    callback: str
    since: str # iso8601
    before: str | None # iso8601
    max_pages: int
    page_size: int

    def to_dict(self):
        """Return a JSON-serializable dict (for json.dumps or requests)."""
        return asdict(self)

@dataclass
class ViperAsset:
    """Data for a viper asset."""

    id: int
    network_segment: str
    cpe: str
    role: str
    upstream_api: str # asset endpoint url: {BASE_URL}/api/assets/{id}/
    hostname: str
    mac_address: str
    serial_number: str
    location: dict[str, str]
    status: str
    vendorID: str

    def __init__(self, asset: Asset):
        self.id = asset.id
        self.name = asset.name
        self.ip_address = asset.ip_address
        self.mac_address = str(asset.mac_address)
        self.vendor = asset.manufacturer
        self.model = asset.model
        self.serial_number = asset.serial_number
        self.udi = asset.udi
        self.network_segment = "" # TODO: get network segment from asset.network_qset()
        self.cpe = "" # TODO: get cpe from asset.cpe_qset()
        self.role = ""
        self.upstream_api = ""
        self.hostname = asset.hostname or ""
        # Coerce to str so payload is JSON-serializable (Asset uses netaddr.EUI / InetAddress)
        self.mac_address = str(asset.mac_address) if asset.mac_address else ""
        self.serial_number = asset.serial_number or ""
        self.location = {} # TODO: custom fields?
        self.status = "active" # TODO: how do we want to determine this?
        self.vendorID = str(asset.nic_vendor)

    def to_dict(self):
        """Return a JSON-serializable dict (for json.dumps or requests)."""
        return asdict(self)

@dataclass
class ViperWebhookResponse:
    """Response for a viper webhook."""

    items: list[ViperAsset]
    page: int
    page_size: int
    total: int
    total_pages: int
    since: str
    before: str | None = None
    # settings?
    webhook_path: str = "/api/viper/webhook/"

    def to_dict(self):
        """Return a JSON-serializable dict (for json.dumps or requests)."""
        base = asdict(self)
        base["next_page"] = self.next_page
        base["previous_page"] = self.previous_page
        return base

    def _gen_page(self, page: int) -> str:
        """Generate a page URL based on the page number, page size, and last sync time."""
        params = f"page={page}&page_size={self.page_size}&since={self.since}"
        if self.before:
            params += f"&before={self.before}"
        return f"{settings.BASE_URL}{self.webhook_path}?{params}"

    @property
    def next_page(self) -> str | None:
        """Return the URL to the next page."""
        if self.page >= self.total_pages:
            return None
        if hasattr(self, "_next_page"):
            return self._next_page
        self._next_page = self._gen_page(self.page + 1)
        return self._next_page

    @property
    def previous_page(self) -> str | None:
        """Return the URL to the previous page."""
        if self.page <= 1:
            return None
        if hasattr(self, "_previous_page"):
            return self._previous_page
        self._previous_page = self._gen_page(self.page - 1)
        return self._previous_page

@dataclass
class ViperWebhookResponseList:
    @staticmethod
    def from_request(request: ViperWebhookRequest) -> Generator[ViperWebhookResponse, None, None]:
        Asset = apps.get_model("bf_opencore", "Asset")
        assets = Asset.objects.filter(last_pinged__gte=request.since)
        if request.before:
            assets = assets.filter(last_pinged__lte=request.before)
        assets = assets.order_by("last_pinged").all()
        total = assets.count()
        total_pages = math.ceil(total / request.page_size)
        page = 1
        for i in range(0, len(assets), request.page_size):
            if page > request.max_pages:
                raise ValueError(f"Max pages exceeded: {request.max_pages}")
            assets_chunk = assets[i:i + request.page_size]
            response = ViperWebhookResponse(
                items=assets_chunk,
                page=page,
                page_size=request.page_size,
                total=total,
                total_pages=total_pages,
                since=request.since,
                before=request.before,
            )
            page += 1
            yield response


