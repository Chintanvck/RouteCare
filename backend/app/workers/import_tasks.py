"""
RouteCare AI - Import background tasks.

Thin dispatchers only - all actual logic lives in app.services.import_service
as plain functions taking an explicit `db: Session`, so it's directly
unit-testable against the SQLite test database without a real broker
(see backend/tests/test_imports_validation.py, which calls
run_row_validation/run_import_execution directly rather than through Celery).
"""

import uuid

from app.database.session import SessionLocal
from app.services import import_service
from app.workers.celery_app import celery_app


@celery_app.task(name="imports.validate")
def validate_import_task(import_id: str) -> None:
    db = SessionLocal()
    try:
        import_service.run_row_validation(db, uuid.UUID(import_id))
    finally:
        db.close()


@celery_app.task(name="imports.execute")
def execute_import_task(import_id: str, include_duplicates: bool) -> None:
    db = SessionLocal()
    try:
        import_service.run_import_execution(db, uuid.UUID(import_id), include_duplicates=include_duplicates)
    finally:
        db.close()
