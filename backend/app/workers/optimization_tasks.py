"""
RouteCare AI - Schedule optimization background task.

Thin dispatcher only, mirroring app.workers.import_tasks - all actual
logic lives in app.services.optimization_service.run_optimization as a
plain function taking an explicit `db: Session`, directly callable from
tests without a real broker (see tests/conftest.py's
sync_optimization_tasks fixture).
"""

import uuid

from app.database.session import SessionLocal
from app.services import optimization_service
from app.workers.celery_app import celery_app


@celery_app.task(name="optimization.run")
def run_optimization_task(optimization_request_id: str) -> None:
    db = SessionLocal()
    try:
        optimization_service.run_optimization(db, uuid.UUID(optimization_request_id))
    finally:
        db.close()
