import logging

import requests
from celery import Task as BaseTask

from bf_opencore.celery import celery_app
from bf_opencore.models import ViperWebhookJob
from bf_opencore.models.viper import ViperWebhookRequest, ViperWebhookResponseList

logger = logging.getLogger(__name__)


class Task(BaseTask):
    # https://docs.celeryq.dev/en/main/userguide/tasks.html#Task.autoretry_for
    max_retries = 5
    retry_backoff = True
    retry_backoff_max = 60  # seconds
    retry_jitter = True
    dont_auto_retry_for = (TypeError,)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"[!!] {task_id} failed: {exc}")


@celery_app.task(base=Task)
def viper_webhook(data: dict, request_id: str = ""):
    """Process a viper webhook."""
    viper_data = ViperWebhookRequest(**data)
    logger.info(f"Processing viper webhook: {viper_data}")
    if request_id:
        ViperWebhookJob.objects.filter(pk=request_id).update(status=ViperWebhookJob.Status.STARTED)
    try:
        response_list = ViperWebhookResponseList.from_request(viper_data, request_id=request_id)
        for response in response_list:
            as_dict = response.to_dict()
            requests.post(
                viper_data.callback,
                json=as_dict,
                headers={"Content-Type": "application/json"},
            )
    except Exception:
        if request_id:
            ViperWebhookJob.objects.filter(pk=request_id).update(status=ViperWebhookJob.Status.ERROR)
        raise
    if request_id:
        ViperWebhookJob.objects.filter(pk=request_id).update(status=ViperWebhookJob.Status.FINISHED)
