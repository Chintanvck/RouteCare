"""
RouteCare AI - Celery application.

Run a worker with:

    celery -A app.workers.celery_app worker --loglevel=info

`task_serializer`/`accept_content`/`result_serializer` are pinned to
"json" explicitly rather than left at Celery's historical default -
Celery can use pickle for serialization, which executes arbitrary code
on deserialization if the broker/result backend is ever compromised or
misconfigured. JSON has no such risk.

Task modules are imported explicitly at the bottom of this file rather
than via `autodiscover_tasks` - autodiscover only looks for a module
literally named "tasks" per package, which stopped covering everything
once `import_tasks.py` was added alongside `tasks.py`. Both modules
import `celery_app` back from here; that's safe specifically because
the import happens after `celery_app` is already bound above, so the
partially-initialized module in sys.modules already has the name they need.
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
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    # Phase 9 hardening - see Settings.CELERY_TASK_SOFT_TIME_LIMIT_SECONDS's docstring.
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT_SECONDS,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT_SECONDS,
)

from app.workers import import_tasks, optimization_tasks, tasks  # noqa: E402,F401
