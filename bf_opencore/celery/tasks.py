from bf_opencore.celery import celery_app
from celery import Task as BaseTask
from bf_opencore.models.viper import ViperWebhookRequest, ViperWebhookResponseList

import logging
import requests

logger = logging.getLogger(__name__)

class Task(BaseTask):
    # https://docs.celeryq.dev/en/main/userguide/tasks.html#Task.autoretry_for
    max_retries = 5
    retry_backoff = True
    retry_backoff_max = 10 # seconds
    retry_jitter = True
    dont_auto_retry_for = (TypeError,)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"[!!] {task_id} failed: {exc}")

@celery_app.task(base=Task)
def viper_webhook(data: dict):
    """Process a viper webhook."""
    viper_data = ViperWebhookRequest(**data)
    logger.info(f"Processing viper webhook: {viper_data}")
    response_list= ViperWebhookResponseList.from_request(viper_data)
    for response in response_list:
        as_dict = response.to_dict()
        requests.post(viper_data.callback, json=as_dict, headers={'Content-Type': 'application/json'})

