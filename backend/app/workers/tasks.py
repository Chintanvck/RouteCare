"""
RouteCare AI - Celery tasks.

`ping` exists only to verify the worker/broker/backend wiring end to
end (see backend/tests/test_workers.py). Business tasks (Excel import
processing, route recalculation, ...) are added starting Phase 3+ -
none belong here yet.
"""

from app.workers.celery_app import celery_app


@celery_app.task(name="workers.ping")
def ping() -> str:
    return "pong"
