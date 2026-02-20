"""
Celery instance for integrations.

One instance of Celery lives in this file.  All tasks in the integrations will
use this instance.

Based on Celery documentation:
http://docs.celeryproject.org/en/latest/getting-started/first-steps-with-celery.html

Quick start (from root blueflow/ directory)
$ celery -A bf_opencore.celery worker --loglevel=info &
...
[2017-06-30 16:36:12,453: INFO/MainProcess] celery@manzana.local ready.
$ python
>>> import bf_opencore.celery
>>> bf_opencore.celery.celery_app.tasks.ping.main.delay(hostname='localhost')
<AsyncResult: e8cfbb56-eca7-491d-a3a3-c15819cad8b8>
"""
import celery
from dataclasses import dataclass
import logging
import requests
from django.apps import apps
from django.conf import settings
from bf_opencore.models import Asset
import json
import math

# register signals
from bf_opencore import signals

logger = logging.getLogger(__name__)

# Create a Celery instance (sometimes called an app)
# Based on Celery documentation found at
#
# Celery docs
# http://docs.celeryproject.org/en/latest/getting-started/next-steps.html
# http://docs.celeryproject.org/en/latest/reference/celery.html#celery.Celery.config_from_object
# http://docs.celeryproject.org/en/latest/userguide/configuration.html
celery_app = celery.Celery('bf_opencore')

# Use Django settings module for configuration
#
# Any configuration parameter that starts with CELERY_ will be read.  See
# notes in settings/defaults.py about logging configuration.  Search for
# "CELERY_WORKER_LOG_FORMAT".
#
# Celery docs
# http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html
celery_app.config_from_object(
    'django.conf:settings',
    namespace='CELERY',
    silent=False,
)

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
        self.network_segment = asset.groups.first().name
        self.cpe = asset.custom_fields.get('cpe').value
        self.role = asset.category
        self.upstream_api = f"{settings.BASE_URL}/api/assets/{asset.id}/"
        self.hostname = asset.hostname
        self.mac_address = asset.mac_address
        self.serial_number = asset.serial_number

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


@celery_app.task
def viper_webhook(viper_data: ViperWebhookRequest):
    """Process a viper webhook."""
    logger.info(f"Processing viper webhook: {viper_data}")
    Asset = apps.get_model('bf_opencore', 'Asset')
    assets = Asset.objects.filter(last_pinged__gte=viper_data.since).filter(last_pinged__lte=viper_data.before).order_by('last_pinged').all()
    total = assets.count()
    total_pages = math.ceil(total / viper_data.page_size)
    for i in range(0, len(assets), viper_data.page_size):
        assets_chunk = assets[i:i + viper_data.page_size]
        viper_assets = [ViperAsset(asset) for asset in assets_chunk]
        viper_response = ViperWebhookResponse(
            items=viper_assets,
            page=viper_data.page,
            page_size=viper_data.page_size,
            total=total,
            total_pages=total_pages,
            next_page=None,
            previous_page=None
        )
        requests.post(viper_data.callback, json.dumps(viper_response))