import logging
from typing import Any

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


def _send_viper_payload(viper_data: ViperWebhookRequest, request_id: str) -> str:
    """Send viper payload, logging partial errors.

    We may want to consider logging partial errors and attempting to
    send the remaining data anyway.
    Wrapping each post in its own celery task would be simple enough.
    """
    import json

    response_list = ViperWebhookResponseList.from_request(
        viper_data, request_id=request_id
    )
    viper_responses = []
    for response in response_list:
        as_dict = response.to_dict()
        v_res = requests.post(
            viper_data.callback,
            json=as_dict,
            headers={"Content-Type": "application/json"},
        )
        if v_res.status_code >= 400:
            return json.dumps(v_res.json(), indent=4)
        v_res.raise_for_status()
        viper_responses.append(v_res.json())
    return json.dumps(viper_responses, indent=4)


@celery_app.task(base=Task)
def viper_webhook(data: dict[str, Any], request_id: str = "") -> str:
    """Process a viper webhook."""
    viper_data = ViperWebhookRequest(**data)
    logger.info("Processing viper webhook: %s", viper_data)
    if request_id:
        _ = ViperWebhookJob.objects.filter(pk=request_id).update(
            status=ViperWebhookJob.Status.STARTED
        )
    try:
        res = _send_viper_payload(viper_data, request_id)
        logger.info("Job completed with respons: %", res)
        if request_id:
            _ = ViperWebhookJob.objects.filter(pk=request_id).update(
                status=ViperWebhookJob.Status.FINISHED
            )
        return res
    except Exception as e:
        if request_id:
            _ = ViperWebhookJob.objects.filter(pk=request_id).update(
                status=ViperWebhookJob.Status.ERROR
            )
        logger.warning("Job failed with err: %", str(e))
        return str(e)
