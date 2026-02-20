from dataclasses import dataclass, asdict
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
        self.mac_address = asset.mac_address
        self.vendor = asset.manufacturer
        self.model = asset.model
        self.serial_number = asset.serial_number
        self.udi = asset.udi
        self.network_segment = '' # TODO: get network segment from asset.network_qset()
        self.cpe = '' # TODO: get cpe from asset.cpe_qset()
        self.role = ''
        self.upstream_api = ''
        self.hostname = asset.hostname
        self.mac_address = asset.mac_address
        self.serial_number = asset.serial_number
        self.location = asset.location
        self.status = asset.status
        self.vendorID = asset.vendorID

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
    next_page: str | None # url to the next page: {BASE_URL}/api/assets/?page={page+1}&page_size={page_size}
    previous_page: str | None # url to the previous page: {BASE_URL}/api/assets/?page={page-1}&page_size={page_size}

    def to_dict(self):
        """Return a JSON-serializable dict (for json.dumps or requests)."""
        return asdict(self)
