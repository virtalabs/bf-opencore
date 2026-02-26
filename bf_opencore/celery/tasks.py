from bf_opencore.celery import celery_app
from bf_opencore.models.viper import ViperWebhookRequest, ViperWebhookResponseList

import logging
import requests

logger = logging.getLogger(__name__)

@celery_app.task
def viper_webhook(data: dict):
    """Process a viper webhook."""
    viper_data = ViperWebhookRequest(**data)
    logger.info(f"Processing viper webhook: {viper_data}")
    response_list= ViperWebhookResponseList.from_request(viper_data)
    for response in response_list:
        as_dict = response.to_dict()
        requests.post(viper_data.callback, json=as_dict, headers={'Content-Type': 'application/json'})
