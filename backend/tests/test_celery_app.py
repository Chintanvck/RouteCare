"""
RouteCare AI - Celery app configuration regression coverage.

Phase 12 (free-tier deployment) found a real production bug: `celery_app.py`
used to configure a Redis result backend (`backend=settings.REDIS_URL`)
alongside the broker. Upstash's `rediss://` (TLS) URL made Celery's own
Redis backend client raise at construction time - it requires an explicit
`ssl_cert_reqs` query param in a Celery-specific format
(`CERT_REQUIRED`/`CERT_OPTIONAL`/`CERT_NONE`), which conflicts with plain
redis-py's `from_url` parser for the *same* setting (`required`/`optional`/
`none`, no `CERT_` prefix) - the one already used for health checks and
rate limiting. The same `REDIS_URL` value cannot satisfy both parsers at
once. This broke `.delay()` for every Celery task in production, even with
`CELERY_TASK_ALWAYS_EAGER=true` - the crash happens in `send_task()`'s
unconditional `self.backend.on_task_call(...)` bookkeeping, before eager
mode ever gets a chance to short-circuit into local execution.

The fix: don't configure a result backend at all. Nothing in this codebase
ever reads a task's result via Celery's own AsyncResult/.get() - progress
is tracked through OptimizationRequest.status/ImportJob.status DB columns
instead - so the backend was dead weight, and removing it sidesteps the
parser conflict entirely (Celery defaults to a real no-op `DisabledBackend`
when none is configured).

These tests run fully offline: a `rediss://` broker URL is only ever used
to construct connection objects, never actually connected to, for a task
that runs eagerly - proven by the fact that constructing the *backend*
this way was what raised immediately (a synchronous URL-parsing error, no
socket ever opened), while the broker is never touched at all when
`task_always_eager=True` short-circuits into local execution.
"""

from celery import Celery

from app.workers.celery_app import celery_app


def test_real_celery_app_has_no_result_backend() -> None:
    """Regression guard: if `backend=` is ever reintroduced to celery_app.py, this fails instead
    of the app crashing on every task dispatch in production the next time someone deploys."""
    assert type(celery_app.backend).__name__ == "DisabledBackend"


def test_eager_task_dispatch_succeeds_with_tls_redis_broker_url() -> None:
    """Mirrors celery_app.py's exact construction (broker only, no backend) against a `rediss://`
    URL shaped like Upstash's - proving `.delay()` doesn't blow up the way it did before this fix,
    without needing a real reachable Redis instance (eager mode never actually connects)."""
    app = Celery("regression-test", broker="rediss://default:fake-token@fake-host.upstash.io:6379")
    app.conf.update(task_always_eager=True)

    @app.task
    def add(x: int, y: int) -> int:
        return x + y

    result = add.delay(2, 3)
    assert result.get() == 5


def test_configuring_a_tls_redis_backend_reproduces_the_original_bug() -> None:
    """Documents *why* the fix is "no backend" rather than "a correctly-encoded backend URL" -
    Celery's Redis backend genuinely cannot be constructed from a bare `rediss://` URL, confirming
    this wasn't a one-off Upstash quirk but a real Celery/redis-py parser mismatch worth avoiding
    entirely rather than working around with URL formatting."""
    app = Celery(
        "regression-test-broken",
        broker="rediss://default:fake-token@fake-host.upstash.io:6379",
        backend="rediss://default:fake-token@fake-host.upstash.io:6379",
    )
    app.conf.update(task_always_eager=True)

    @app.task
    def add(x: int, y: int) -> int:
        return x + y

    try:
        add.delay(2, 3)
    except ValueError as exc:
        assert "ssl_cert_reqs" in str(exc)
    else:
        raise AssertionError(
            "Expected constructing a rediss:// Celery result backend without ssl_cert_reqs to "
            "raise ValueError - if this now succeeds, a Celery/redis-py version bump may have "
            "changed this behavior and the backend=None fix in celery_app.py may be worth revisiting."
        )
