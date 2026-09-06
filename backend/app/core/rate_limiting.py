"""
RouteCare AI - Rate limiting (Phase 9).

Redis-backed fixed-window counters, reusing the exact same
`app.core.cache.get_redis_client()` connection every other Redis
consumer (caching, health checks) already uses - no second Redis
client/config to keep in sync, and tests already have a fake in-memory
stand-in wired up for that one function (see tests/conftest.py's
`_fake_redis_cache` fixture), so rate limiting is deterministic in
tests for free.

Fails OPEN, not closed: any Redis error is treated as "not rate
limited" rather than blocking every request when Redis is briefly
unavailable - matches app.core.cache's documented philosophy exactly.
Rate limiting is defense-in-depth here (bcrypt + correct-password-every-
attempt is the real control on login), not the sole safeguard, so
failing open is the right tradeoff over failing closed and taking the
whole API down with Redis.

Two shapes are provided:
- The three named auth dependencies (rate_limit_login/_password_reset/_register)
  bucket by (client IP, email-from-body) so one attacker can't just
  rotate the email field to dodge a per-IP limit, and one compromised
  account can't be hammered past its own limit from many IPs either.
- `rate_limit(bucket, limit=, window_seconds=)` is a factory for
  authenticated "expensive operation" endpoints (import upload,
  optimization requests, geocode, travel-time matrix) - keyed by user_id
  since those endpoints already require auth.
"""

from collections.abc import Callable
from typing import Any

import redis
from fastapi import Request

from app.core import cache as cache_module
from app.core.config import settings
from app.core.exceptions import RateLimitedError
from app.core.logging_config import auth_logger

_RATE_LIMIT_MESSAGE = "Too many requests. Please wait a while before trying again."


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _body_field(request: Request, field: str) -> str:
    """Best-effort read of one field from the JSON body for bucketing purposes only - a malformed
    or non-JSON body just falls back to the empty string (IP-only bucketing) rather than ever
    blocking the request itself; real body validation still happens downstream via the route's own
    Pydantic model. Starlette caches the raw body the first time it's read, so this never
    interferes with FastAPI's own subsequent parsing of the same request."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - any parse failure just means "no extra bucketing key"
        return ""
    value = body.get(field) if isinstance(body, dict) else None
    return str(value).strip().lower() if value else ""


def _enforce(*, bucket: str, identifier: str, limit: int, window_seconds: int) -> None:
    key = f"routecare:ratelimit:{bucket}:{identifier}"
    try:
        # Calling this through the module (not `from app.core.cache import get_redis_client`) is
        # deliberate - tests monkeypatch app.core.cache.get_redis_client, and a direct name-import
        # would have captured the original function by value at import time, permanently missing
        # that patch and quietly falling through to a real (and, in a test environment with no
        # Redis running, slow-to-fail) connection attempt on every call.
        client = cache_module.get_redis_client()
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
    except redis.RedisError:
        return
    if count > limit:
        auth_logger.warning("rate_limit_exceeded", extra={"bucket": bucket, "count": count, "limit": limit})
        raise RateLimitedError(_RATE_LIMIT_MESSAGE)


async def rate_limit_login(request: Request) -> None:
    email = await _body_field(request, "email")
    _enforce(
        bucket="login",
        identifier=f"{_client_ip(request)}:{email}",
        limit=settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS,
        window_seconds=settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
    )


async def rate_limit_password_reset(request: Request) -> None:
    email = await _body_field(request, "email")
    _enforce(
        bucket="password_reset",
        identifier=f"{_client_ip(request)}:{email}",
        limit=settings.RATE_LIMIT_PASSWORD_RESET_MAX_ATTEMPTS,
        window_seconds=settings.RATE_LIMIT_PASSWORD_RESET_WINDOW_SECONDS,
    )


async def rate_limit_register(request: Request) -> None:
    _enforce(
        bucket="register",
        identifier=_client_ip(request),
        limit=settings.RATE_LIMIT_REGISTER_MAX_ATTEMPTS,
        window_seconds=settings.RATE_LIMIT_REGISTER_WINDOW_SECONDS,
    )


def rate_limit(bucket: str, *, limit: int, window_seconds: int) -> Callable[..., Any]:
    """Build a dependency that rate-limits one authenticated user against `bucket`, e.g.:

        dependencies=[Depends(rate_limit("import_upload", limit=10, window_seconds=3600))]

    For expensive, already-authenticated operations (Excel import, optimization requests,
    geocoding, travel-time matrices) - per the task's explicit "prevent abusive requests from
    expensive operations" while never rate-limiting internal service calls.
    """
    from fastapi import Depends

    from app.core.dependencies import get_current_user

    def dependency(current_user: Any = Depends(get_current_user)) -> None:
        _enforce(bucket=bucket, identifier=str(current_user.id), limit=limit, window_seconds=window_seconds)

    return dependency
