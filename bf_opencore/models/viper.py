from dataclasses import dataclass
from bf_opencore.models import Asset

@dataclass
class ViperWebhookRequest:
    """Data for a viper webhook."""
    callback: str
    since: str # iso8601 
    before: str # iso8601
    page: int
    page_size: int

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
