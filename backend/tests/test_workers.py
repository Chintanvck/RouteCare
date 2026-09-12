"""
Tests for the Celery infrastructure (app.workers). `ping` is a
throwaway task that exists only to prove the worker/task wiring is
correct end to end. `imports.validate`/`imports.execute` (Phase 3) are
the first real business tasks - their actual logic is tested directly
against the SQLite test DB in test_imports_validation.py/test_imports_confirm.py,
not through Celery dispatch, since the task wrappers open their own
SessionLocal() bound to the real configured DATABASE_URL rather than
the test database. Here we only confirm they're registered.
"""

from app.workers.celery_app import celery_app
from app.workers.tasks import ping


def test_celery_app_uses_json_serialization_only() -> None:
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.result_serializer == "json"


def test_celery_app_broker_comes_from_settings_and_has_no_result_backend() -> None:
    """No result backend is configured on purpose (see test_celery_app.py for the full story) -
    nothing in this codebase reads a task's result via Celery's own AsyncResult/.get(), and a
    Redis-backed one was actively broken against Upstash's rediss:// URL in production."""
    from app.core.config import settings

    assert celery_app.conf.broker_url == settings.REDIS_URL
    assert celery_app.conf.result_backend is None


def test_ping_task_is_registered() -> None:
    assert "workers.ping" in celery_app.tasks


def test_import_tasks_are_registered() -> None:
    assert "imports.validate" in celery_app.tasks
    assert "imports.execute" in celery_app.tasks


def test_ping_task_direct_call_returns_pong() -> None:
    assert ping() == "pong"


def test_ping_task_runs_through_celery_dispatch_in_eager_mode() -> None:
    # Eager mode bypasses the broker/worker entirely, so this verifies the
    # task is correctly wired into Celery's dispatch machinery without
    # needing a real Redis broker running in this environment.
    celery_app.conf.task_always_eager = True
    try:
        result = ping.delay()
        assert result.get(timeout=5) == "pong"
    finally:
        celery_app.conf.task_always_eager = False
