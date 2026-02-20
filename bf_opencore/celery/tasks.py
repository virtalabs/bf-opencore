from bf_opencore.celery import celery_app
from bf_opencore.models.viper import ViperWebhookRequest, ViperWebhookResponse, ViperAsset
from django.apps import apps

import logging
import math
import requests

logger = logging.getLogger(__name__)

@celery_app.task
def viper_webhook(viper_data: dict):
    """Process a viper webhook."""
    viper_data = ViperWebhookRequest(**viper_data)
    logger.info(f"Processing viper webhook: {viper_data}")
    Asset = apps.get_model('bf_opencore', 'Asset')
    assets = Asset.objects.filter(last_pinged__gte=viper_data.since)
    if viper_data.before:
        assets = assets.filter(last_pinged__lte=viper_data.before)
    assets = assets.order_by('last_pinged').all()
    total = assets.count()
    total_pages = math.ceil(total / viper_data.page_size)
    page = 1
    for i in range(0, len(assets), viper_data.page_size):
        if page > viper_data.max_pages:
            raise ValueError(f"Max pages exceeded: {viper_data.max_pages}")
        assets_chunk = assets[i:i + viper_data.page_size]
        viper_assets = [ViperAsset(asset).to_dict() for asset in assets_chunk]
        viper_response = ViperWebhookResponse(
            items=viper_assets,
            page=page,
            page_size=viper_data.page_size,
            total=total,
            total_pages=total_pages,
            next_page=None,
            previous_page=None
        )
        page += 1
        requests.post(viper_data.callback, viper_response.to_dict(), headers={'Content-Type': 'application/json'})