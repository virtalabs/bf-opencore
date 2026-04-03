import logging

import requests
from celery import Task as BaseTask

from blueflow.celery import celery_app
from blueflow.models import ViperWebhookJob
from blueflow.models.viper import ViperWebhookRequest, ViperWebhookResponseList

logger = logging.getLogger(__name__)


class Task(BaseTask):
    # https://docs.celeryq.dev/en/main/userguide/tasks.html#Task.autoretry_for
    max_retries = 5
    retry_backoff = True
    retry_backoff_max = 60  # seconds
    retry_jitter = True
    dont_auto_retry_for = (TypeError,)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error("[!!] %s failed: %s", task_id, exc)

def _send_viper_payload(viper_data: ViperWebhookJob, request_id: str) -> None:
    """Send viper payload, logging partial errors.

    We may want to consider logging partial errors and attempting to
    send the remaining data anyway.
    Wrapping each post in its own celery task would be simple enough.
    """
    response_list = ViperWebhookResponseList.from_request(
        viper_data, request_id=request_id
    )
    for response in response_list:
        as_dict = response.to_dict()
        response = requests.post(
            viper_data.callback,
            json=as_dict,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

@celery_app.task(base=Task)
def viper_webhook(data: dict, request_id: str = ""):
    """Process a viper webhook."""
    viper_data = ViperWebhookRequest(**data)
    logger.info("Processing viper webhook: %s", viper_data)
    if request_id:
        ViperWebhookJob.objects.filter(pk=request_id).update(status=ViperWebhookJob.Status.STARTED)
    try:
        _send_viper_payload(viper_data, request_id)
    except Exception:
        if request_id:
            ViperWebhookJob.objects.filter(pk=request_id).update(status=ViperWebhookJob.Status.ERROR)
        raise
    if request_id:
        ViperWebhookJob.objects.filter(pk=request_id).update(status=ViperWebhookJob.Status.FINISHED)

