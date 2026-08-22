"""
RouteCare AI - Celery application.

Infrastructure only - no business tasks yet (Excel import background
processing lands in Phase 3). Run a worker with:

    celery -A app.workers.celery_app worker --loglevel=info

`task_serializer`/`accept_content`/`result_serializer` are pinned to
"json" explicitly rather than left at Celery's historical default -
Celery can use pickle for serialization, which executes arbitrary code
on deserialization if the broker/result backend is ever compromised or
misconfigured. JSON has no such risk.
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery("routecare", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.autodiscover_tasks(["app.workers"])
