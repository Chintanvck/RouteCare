"""
Tests for the Celery infrastructure skeleton (app.workers). `ping` is a
throwaway task that exists only to prove the worker/task wiring is
correct end to end - no business tasks exist yet.
"""

from app.workers.celery_app import celery_app
from app.workers.tasks import ping


def test_celery_app_uses_json_serialization_only() -> None:
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.result_serializer == "json"


def test_celery_app_broker_and_backend_come_from_settings() -> None:
    from app.core.config import settings

    assert celery_app.conf.broker_url == settings.REDIS_URL
    assert celery_app.conf.result_backend == settings.REDIS_URL


def test_ping_task_is_registered() -> None:
    assert "workers.ping" in celery_app.tasks


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
