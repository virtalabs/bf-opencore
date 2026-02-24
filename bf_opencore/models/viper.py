from dataclasses import dataclass, asdict
from django.conf import settings
from bf_opencore.models import Asset

@dataclass
class ViperWebhookRequest:
    """Data for a viper webhook."""
    callback: str
    since: str # iso8601 
    before: str # iso8601
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
    vendorID: int

    def __init__(self, asset: Asset):
        self.id = asset.id
        self.name = asset.name
        self.ip_address = asset.ip_address
        self.mac_address = str(asset.mac_address)
        self.vendor = asset.manufacturer
        self.model = asset.model
        self.serial_number = asset.serial_number
        self.udi = asset.udi
        self.network_segment = '' # TODO: get network segment from asset.network_qset()
        self.cpe = '' # TODO: get cpe from asset.cpe_qset()
        self.role = ''
        self.upstream_api = ''
        self.hostname = asset.hostname or ''
        # Coerce to str so payload is JSON-serializable (Asset uses netaddr.EUI / InetAddress)
        self.mac_address = str(asset.mac_address) if asset.mac_address else ''
        self.serial_number = asset.serial_number or ''
        self.location = {} # TODO: custom fields?
        self.status = 'active' # TODO: how do we want to determine this?
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
    webhook_path = "/api/viper/webhook/"

    def to_dict(self):
        """Return a JSON-serializable dict (for json.dumps or requests)."""
        return asdict(self)

    @property
    def next_page(self):
        """Return the URL to the next page."""
        if self.page + 1 >= self.total_pages:
            return None
        if hasattr(self, '_next_page'):
            return self._next_page
        params_next = f"page={self.page + 1}&page_size={self.page_size}&last_sync={self.last_sync_iso}"
        if self.not_after_iso:
            params_next += f"&not_after={self.not_after_iso}"
        self._next_page = f"{settings.BASE_URL}{self.webhook_path}?{params_next}"
        return self._next_page

    @property
    def previous_page(self):
        """Return the URL to the previous page."""
        if self.page <= 1:
            return None
        if hasattr(self, '_previous_page'):
            return self._previous_page
        params_prev = f"page={self.page - 1}&page_size={self.page_size}&last_sync={self.last_sync_iso}"
        if self.not_after_iso:
            params_prev += f"&not_after={self.not_after_iso}"
        self._previous_page = f"{settings.BASE_URL}{self.webhook_path}?{params_prev}"
        return self.previous_page